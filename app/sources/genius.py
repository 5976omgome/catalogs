"""Genius API — pulls artist Instagram & Facebook links via balanced matching.

Requires a free Client Access Token from https://genius.com/api-clients
Returns: instagram, facebook URLs + match_confidence when available.
Uses shared Session for FD safety.

RATE LIMITING: Genius free tier allows ~2 req/sec. We use a global
lock + sleep to ensure we never exceed this across all worker threads.
On rate-limit responses (HTTP 429, Cloudflare 1015, or 403-HTML block
pages) we apply escalating exponential backoff and, on exhaustion, return
the typed ``RATE_LIMITED`` sentinel rather than silently returning None.

MATCHING: Examines up to 10 search hits using normalized name comparison.
Selects "Exact" (normalized equality) or "Uncertain" (substring/prefix)
matches. Rejects loose guesses — no blind first-hit acceptance.
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

# Per-key rate limiting — each Genius token gets its OWN 2 req/sec budget, so
# N keys deliver ~N x throughput when Genitractor load-balances across them.
_MIN_INTERVAL = 0.5  # 2 requests/second per key — tested safe, no 429s

# Escalating backoff schedule (seconds) applied on rate-limit responses.
_BACKOFF_SCHEDULE = [2, 4, 8, 16, 32]

_key_state_lock = threading.Lock()
_key_states = {}  # token (or "__global__") -> {"lock": Lock, "last": float}


def _state_for(key):
    k = key or "__global__"
    with _key_state_lock:
        st = _key_states.get(k)
        if st is None:
            st = {"lock": threading.Lock(), "last": 0.0}
            _key_states[k] = st
        return st


class _RateLimited:
    """Typed sentinel signalling that Genius rate-limited us past backoff."""
    __slots__ = ()

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<genius.RATE_LIMITED>"


# Module-level singleton — callers compare identity: `result is RATE_LIMITED`.
RATE_LIMITED = _RateLimited()


def _rate_limit(key=None):
    """Per-key non-blocking rate limiter — paces each token independently."""
    st = _state_for(key)
    wait = 0.0
    with st["lock"]:
        now = time.time()
        elapsed = now - st["last"]
        if elapsed < _MIN_INTERVAL:
            wait = _MIN_INTERVAL - elapsed
        st["last"] = now + wait
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


def _request_with_backoff(url, params, headers, key=None, timeout=10):
    """GET with per-key rate limiting + escalating backoff on rate-limit responses.

    Returns the ``requests`` response on success/non-rate-limit status, or the
    typed ``RATE_LIMITED`` sentinel if the backoff schedule is exhausted.
    """
    attempt = 0
    while True:
        _rate_limit(key)
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
# Name Normalization — shared by search matching
# ---------------------------------------------------------------------------

# Join tokens removed during normalization (word boundaries)
_JOIN_TOKENS_RE = re.compile(
    r'\b(feat\.?|featuring|vs\.?|and|&)\b', re.IGNORECASE
)
# NOTE: We do NOT strip standalone "x" as a join token because artist names
# like "X Ambassadors" or literally "X" would be destroyed.


def normalize_name(s: str) -> str:
    """Normalize an artist name for matching comparison.

    Transformation order:
    1. Strip leading/trailing whitespace
    2. Case-fold (lowercase)
    3. Collapse internal whitespace
    4. Strip diacritics (NFKD + ASCII encode)
    5. Remove all punctuation (keep alphanumeric + spaces)
    6. Remove join tokens (feat./featuring/vs/and/&)
    7. Collapse whitespace again after token removal
    8. Remove leading "the "
    9. Final strip
    """
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r'\s+', ' ', s)
    # Strip diacritics
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    # Remove punctuation (keep word chars + spaces)
    s = re.sub(r'[^\w\s]', '', s)
    # Remove join tokens
    s = _JOIN_TOKENS_RE.sub(' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Remove leading "the "
    s = re.sub(r'^the\s+', '', s)
    return s.strip()


# ---------------------------------------------------------------------------
# Social URL Normalization
# ---------------------------------------------------------------------------

def normalize_social_url(platform: str, raw: str) -> str:
    """Normalize a social handle/URL into a full HTTPS URL.

    Args:
        platform: "instagram" or "facebook"
        raw: The raw value from Genius (handle, page name, or full URL)

    Returns:
        Full URL string, or empty string if raw is empty/whitespace.
    """
    if not raw or not raw.strip():
        return ""
    val = raw.strip().lstrip("@").strip("/").strip()
    if not val:
        return ""

    # If already a full URL, pass through (double-prefix protection)
    if val.lower().startswith("http://") or val.lower().startswith("https://"):
        return val

    # Prefix with platform base URL
    if platform == "instagram":
        return f"https://instagram.com/{val}"
    elif platform == "facebook":
        return f"https://facebook.com/{val}"
    return val


# ---------------------------------------------------------------------------
# Cache key helper
# ---------------------------------------------------------------------------

def _cache_key(artist: str) -> str:
    return f"genius_socials:{re.sub(r'[^a-z0-9]', '', artist.lower())}"


# ---------------------------------------------------------------------------
# Main API — balanced artist matching with confidence scoring
# ---------------------------------------------------------------------------

def get_socials(artist: str, key: Optional[str] = None) -> Optional[Union[Dict[str, str], _RateLimited]]:
    """Fetch Instagram & Facebook for an artist from Genius.

    Uses balanced matching: examines up to 10 search hits, picks Exact
    (normalized name equality) or Uncertain (substring/prefix) match.
    Rejects loose guesses entirely — no blind first-hit fallback.

    Args:
        artist: artist name to look up
        key: a specific Genius token to use (for multi-key load-balancing).
             Falls back to the configured/legacy token when omitted.

    Returns:
        dict: {"instagram": url, "facebook": url, "match_confidence": "Exact"|"Uncertain"}
        None: no acceptable match found, or no API key configured
        RATE_LIMITED: Genius rate-limited us past the backoff schedule
    """
    key = key or config.genius_token()
    if not key:
        return None

    cache_key = _cache_key(artist)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached else None

    headers = {"Authorization": f"Bearer {key}"}

    try:
        # Search for artist (Genius search returns songs, we extract artist)
        r = _request_with_backoff(
            f"{_BASE}/search",
            params={"q": artist, "per_page": 10},
            headers=headers,
            key=key,
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

        # --- Balanced matching: examine up to 10 hits ---
        query_norm = normalize_name(artist)
        if not query_norm:
            cache.put(cache_key, {})
            return None

        artist_id = None
        confidence = None
        best_close = None  # (artist_id, name) for the best Close match

        for hit in hits[:10]:
            result = hit.get("result", {})
            primary = result.get("primary_artist", {})
            if not primary:
                continue
            hit_name = primary.get("name", "")
            hit_norm = normalize_name(hit_name)
            if not hit_norm:
                continue

            # Exact match — normalized equality
            if hit_norm == query_norm:
                artist_id = primary.get("id")
                confidence = "Exact"
                break

            # Close match — one is a prefix/substring of the other
            if best_close is None:
                if hit_norm in query_norm or query_norm in hit_norm:
                    best_close = (primary.get("id"), "Uncertain")

        # Use best close match if no exact found
        if artist_id is None and best_close is not None:
            artist_id, confidence = best_close

        if artist_id is None:
            cache.put(cache_key, {})
            return None

        # Get full artist object with social links
        r2 = _request_with_backoff(
            f"{_BASE}/artists/{artist_id}",
            params={"text_format": "plain"},
            headers=headers,
            key=key,
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

        # Extract and normalize Instagram + Facebook only
        ig_raw = artist_data.get("instagram_name") or ""
        fb_raw = artist_data.get("facebook_name") or ""

        instagram = normalize_social_url("instagram", ig_raw)
        facebook = normalize_social_url("facebook", fb_raw)

        socials = {
            "instagram": instagram,
            "facebook": facebook,
            "match_confidence": confidence,
        }

        has_any = bool(instagram or facebook)
        if has_any:
            found_keys = []
            if instagram:
                found_keys.append("instagram")
            if facebook:
                found_keys.append("facebook")
            print(f"[genius] \u2713 '{artist}' \u2192 {found_keys} ({confidence})", flush=True)

        cache.put(cache_key, socials)
        return socials if has_any or confidence else None

    except Exception as e:
        print(f"[genius] Error for '{artist}': {e}", flush=True)
        return None
