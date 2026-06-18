"""Genius API — pulls artist social media links.

Requires a free Client Access Token from https://genius.com/api-clients
Returns: Instagram and Facebook profile URLs when available, plus a
``match_confidence`` flag (Exact|Uncertain) describing how confidently the
resolved Genius artist matches the queried name.
Uses shared Session for FD safety.

RATE LIMITING: Genius free tier allows ~2 req/sec. We use a global
lock + sleep to ensure we never exceed this across all worker threads.
On rate-limit responses (HTTP 429, Cloudflare 1015, or 403-HTML block
pages) we apply escalating exponential backoff and, on exhaustion, return
the typed ``RATE_LIMITED`` sentinel rather than silently returning None.
"""
import re
import time
import random
import threading
import unicodedata
from typing import Optional, Dict, Union

from app.sources._http import ai_session as _s
from app import config, cache

_BASE = "https://api.genius.com"

# Global rate limiter — 2 req/sec is the safe max for Genius free tier
_genius_lock = threading.Lock()
_last_request_time = 0.0
_MIN_INTERVAL = 0.5  # 2 requests/second — tested safe, no 429s

# Escalating backoff schedule (seconds) applied on rate-limit responses.
_BACKOFF_SCHEDULE = [2, 4, 8, 16, 32]


class _RateLimited:
    """Typed sentinel signalling that Genius rate-limited us past backoff."""
    __slots__ = ()

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<genius.RATE_LIMITED>"


# Module-level singleton — callers compare identity: `result is RATE_LIMITED`.
RATE_LIMITED = _RateLimited()


def _rate_limit():
    """Non-blocking rate limiter — computes wait, releases lock, then sleeps."""
    global _last_request_time
    wait = 0.0
    with _genius_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < _MIN_INTERVAL:
            wait = _MIN_INTERVAL - elapsed
        _last_request_time = now + wait
    if wait > 0:
        time.sleep(wait)


def _is_rate_limited(r) -> bool:
    """Detect HTTP 429, Cloudflare 1015, and 403-HTML block pages."""
    if r.status_code == 429:
        return True
    ct = (r.headers.get("Content-Type") or "").lower()
    try:
        body_head = (r.text or "")[:512].lower()
    except Exception:
        body_head = ""
    # Cloudflare "error code: 1015" rate-limit page
    if "1015" in body_head and ("error code" in body_head or "rate" in body_head):
        return True
    # 403 served as an HTML block/challenge page (Cloudflare WAF)
    if r.status_code == 403 and ("text/html" in ct or "<html" in body_head):
        return True
    return False


def _request_with_backoff(url, params, headers, timeout=10):
    """GET with rate limiting + escalating backoff on rate-limit responses.

    Returns the ``requests`` response on success/non-rate-limit status, or the
    typed ``RATE_LIMITED`` sentinel if the backoff schedule is exhausted.
    """
    attempt = 0
    while True:
        _rate_limit()
        r = _s.get(url, params=params, headers=headers, timeout=timeout)
        # 401 is an auth problem, not a rate limit — let the caller handle it.
        if r.status_code == 401:
            return r
        if _is_rate_limited(r):
            if attempt >= len(_BACKOFF_SCHEDULE):
                print(f"[genius] rate-limited (status {r.status_code}) — backoff exhausted", flush=True)
                return RATE_LIMITED
            base = _BACKOFF_SCHEDULE[attempt]
            wait = base + random.uniform(0.0, base * 0.25)  # jitter
            print(f"[genius] rate-limited (status {r.status_code}) — backing off {wait:.1f}s", flush=True)
            time.sleep(wait)
            attempt += 1
            continue
        return r


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------
# Join/feature tokens removed before punctuation stripping. ``&`` is matched
# as a literal symbol; ``x`` and ``and`` only as whole words so "Maxwell" and
# "Anderson" are not damaged.
_JOIN_RE = re.compile(
    r"\bfeaturing\b|\bfeat\.?\b|\bft\.?\b|&|\band\b|\bx\b"
)


def _normalize_name(s: str) -> str:
    """Richer, ordered artist-name normalizer used for balanced matching.

    Applies, in this exact sequence:
      1. null guard
      2. NFKD decomposition + diacritic/accent strip
      3. case-fold
      4. remove join/feature tokens (feat./featuring/ft./&/whole-word x/and)
      5. strip punctuation to ``[a-z0-9\\s]``
      6. remove a single leading "the "
      7. collapse internal whitespace
      8. trim
    """
    if not s:
        return ""
    # 2. strip accents/diacritics
    decomposed = unicodedata.normalize("NFKD", s)
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    # 3. case-fold
    folded = no_accents.casefold()
    # 4. remove join/feature tokens
    joined = _JOIN_RE.sub(" ", folded)
    # 5. strip punctuation (keep alnum + whitespace)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", joined)
    # 6. remove a single leading "the"
    cleaned = re.sub(r"^\s*the\s+", " ", cleaned)
    # 7-8. collapse whitespace + trim
    return re.sub(r"\s+", " ", cleaned).strip()


def _cache_key_normalize(s: str) -> str:
    """Legacy alphanumeric-only normalizer — kept stable for cache keys.

    Used ONLY to derive ``cache_key`` so existing cache entries are not
    orphaned by the richer matching normalizer above.
    """
    return re.sub(r"[^a-z0-9]", "", s.lower()) if s else ""


# ---------------------------------------------------------------------------
# IG / FB handle → URL normalization (single source of truth)
# ---------------------------------------------------------------------------
def ig_to_url(raw: str) -> str:
    """Normalize an Instagram handle or URL into a canonical profile URL.

    - case-insensitive ``http(s)://`` passthrough (double-prefix protection)
    - empty / whitespace-only → ``""``
    - else strip ``@``, surrounding whitespace, leading/trailing slashes,
      then prepend exactly one ``https://instagram.com/``
    """
    v = (raw or "").strip()
    if not v:
        return ""
    if v.lower().startswith(("http://", "https://")):
        return v
    v = v.lstrip("@").strip()
    v = v.strip("/")
    if not v:
        return ""
    return f"https://instagram.com/{v}"


def fb_to_url(raw: str) -> str:
    """Normalize a Facebook handle or URL into a canonical profile URL.

    - case-insensitive ``http(s)://`` passthrough (double-prefix protection)
    - empty / whitespace-only → ``""``
    - else strip surrounding whitespace and leading/trailing slashes, then
      prepend exactly one ``https://facebook.com/``
    """
    v = (raw or "").strip()
    if not v:
        return ""
    if v.lower().startswith(("http://", "https://")):
        return v
    v = v.strip("/")
    if not v:
        return ""
    return f"https://facebook.com/{v}"


def get_socials(artist: str) -> Optional[Union[Dict[str, str], _RateLimited]]:
    """Fetch Instagram/Facebook handles for an artist from Genius.

    Returns one of:
      - ``{"instagram": <url-or-"">, "facebook": <url-or-"">,
         "match_confidence": "Exact"|"Uncertain"}`` on an accepted match,
      - ``None`` if no key configured, no hits, or no acceptable match,
      - the ``RATE_LIMITED`` sentinel if Genius rate-limited us past backoff.

    Matching examines up to the first 10 search hits in Genius order: an exact
    normalized-equality match wins (``Exact``); otherwise the lowest-index
    close (normalized prefix/substring) match wins (``Uncertain``); otherwise
    the artist is rejected (negative-cached) and ``None`` is returned.
    """
    key = config.genius_token()
    if not key:
        return None

    cache_key = f"genius_socials:{_cache_key_normalize(artist)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached else None

    headers = {"Authorization": f"Bearer {key}"}

    try:
        # Search for artist (Genius search returns songs; extract the artist).
        r = _request_with_backoff(
            f"{_BASE}/search",
            params={"q": artist, "per_page": 10},
            headers=headers,
            timeout=10,
        )
        if r is RATE_LIMITED:
            return RATE_LIMITED
        if r.status_code == 401:
            print(f"[genius] 401 Unauthorized — token may be invalid", flush=True)
            return None
        r.raise_for_status()

        data = r.json()
        hits = data.get("response", {}).get("hits", [])

        if not hits:
            cache.put(cache_key, {})
            return None

        # --- Balanced top-10 artist matching ---------------------------------
        nq = _normalize_name(artist)
        exact_id = None
        close_id = None

        for hit in hits[:10]:
            primary = hit.get("result", {}).get("primary_artist", {}) or {}
            nh = _normalize_name(primary.get("name", ""))
            if not nh:
                continue  # guard degenerate empty normalized hit names
            if nh == nq:
                exact_id = primary.get("id")
                break  # exact is unbeatable; stop scanning
            if close_id is None and nq and (
                nh.startswith(nq) or nq.startswith(nh) or nq in nh or nh in nq
            ):
                # keep the first (lowest-index, most-relevant) close match
                close_id = primary.get("id")

        if exact_id is not None:
            artist_id, confidence = exact_id, "Exact"
        elif close_id is not None:
            artist_id, confidence = close_id, "Uncertain"
        else:
            cache.put(cache_key, {})  # negative cache
            return None

        if artist_id is None:
            cache.put(cache_key, {})
            return None

        # Get full artist object with social links.
        r2 = _request_with_backoff(
            f"{_BASE}/artists/{artist_id}",
            params={"text_format": "plain"},
            headers=headers,
            timeout=10,
        )
        if r2 is RATE_LIMITED:
            return RATE_LIMITED
        if r2.status_code != 200:
            cache.put(cache_key, {})
            return None

        artist_data = r2.json().get("response", {}).get("artist", {})
        if not artist_data:
            cache.put(cache_key, {})
            return None

        ig = artist_data.get("instagram_name") or ""
        fb = artist_data.get("facebook_name") or ""

        result = {
            "instagram": ig_to_url(ig),
            "facebook": fb_to_url(fb),
            "match_confidence": confidence,
        }

        if result["instagram"] or result["facebook"]:
            print(f"[genius] \u2713 '{artist}' \u2192 {confidence}", flush=True)

        cache.put(cache_key, result)
        return result

    except Exception as e:
        print(f"[genius] Error for '{artist}': {e}", flush=True)
        return None
