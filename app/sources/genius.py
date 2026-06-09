"""Genius API — pulls artist social media links.

Requires a free Client Access Token from https://genius.com/api-clients
Returns: instagram, twitter, facebook handles when available.
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


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower()) if s else ""


def get_socials(artist: str) -> Optional[Union[Dict[str, str], _RateLimited]]:
    """Fetch social media handles for an artist from Genius.

    Returns dict like:
        {"instagram": "handle", "twitter": "handle", "facebook": "page_url"}
    or None if artist not found or no key configured, or the ``RATE_LIMITED``
    sentinel if Genius rate-limited us past the backoff schedule.
    """
    key = config.genius_token()
    if not key:
        return None

    cache_key = f"genius_socials:{_normalize(artist)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached else None

    headers = {"Authorization": f"Bearer {key}"}

    try:
        # Search for artist (Genius search returns songs, we extract artist from them)
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

        # Find the artist ID from search results
        an = _normalize(artist)
        artist_id = None
        artist_match_name = None

        for hit in hits:
            result = hit.get("result", {})
            primary = result.get("primary_artist", {})
            if primary:
                name = _normalize(primary.get("name", ""))
                if name == an or an in name or name in an:
                    artist_id = primary.get("id")
                    artist_match_name = primary.get("name", "")
                    break

        if not artist_id:
            first_hit = hits[0].get("result", {}).get("primary_artist", {})
            if first_hit:
                first_name = _normalize(first_hit.get("name", ""))
                if len(an) >= 3 and (an[:3] in first_name or first_name[:3] in an):
                    artist_id = first_hit.get("id")
                    artist_match_name = first_hit.get("name", "")

        if not artist_id:
            cache.put(cache_key, {})
            return None

        # Get full artist object with social links
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

        socials = {}
        ig = artist_data.get("instagram_name") or ""
        tw = artist_data.get("twitter_name") or ""
        fb = artist_data.get("facebook_name") or ""

        if ig:
            socials["instagram"] = ig.strip().lstrip("@")
        if tw:
            socials["twitter"] = tw.strip().lstrip("@")
        if fb:
            socials["facebook"] = fb.strip()

        # Store the Genius profile URL for reference (no direct website field).
        genius_url = artist_data.get("url") or ""
        if genius_url:
            socials["genius_url"] = genius_url

        if socials:
            found_keys = [k for k in socials if k != "genius_url"]
            if found_keys:
                print(f"[genius] \u2713 '{artist}' \u2192 {found_keys}", flush=True)

        cache.put(cache_key, socials if socials else {})
        return socials if socials else None

    except Exception as e:
        print(f"[genius] Error for '{artist}': {e}", flush=True)
        return None
