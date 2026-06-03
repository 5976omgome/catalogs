"""Genius API — pulls artist social media links.

Requires a free Client Access Token from https://genius.com/api-clients
Returns: instagram, twitter, facebook handles when available.
Uses shared Session for FD safety.

RATE LIMITING: Genius free tier allows ~5 req/sec. We use a global
lock + sleep to ensure we never exceed this across all worker threads.
"""
import re
import time
import threading
from typing import Optional, Dict

from app.sources._http import ai_session as _s
from app import config, cache

_BASE = "https://api.genius.com"

# Global rate limiter — 2 req/sec is the safe max for Genius free tier
_genius_lock = threading.Lock()
_last_request_time = 0.0
_MIN_INTERVAL = 0.5  # 2 requests/second — tested safe, no 429s


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


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower()) if s else ""


def get_socials(artist: str) -> Optional[Dict[str, str]]:
    """Fetch social media handles for an artist from Genius.

    Returns dict like:
        {"instagram": "handle", "twitter": "handle", "facebook": "page_url"}
    or None if artist not found or no key configured.
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
        # Rate limit before each API call
        _rate_limit()

        # Search for artist (Genius search returns songs, we extract artist from them)
        r = _s.get(
            f"{_BASE}/search",
            params={"q": artist, "per_page": 10},
            headers=headers,
            timeout=10,
        )
        if r.status_code == 401:
            print(f"[genius] 401 Unauthorized — token may be invalid", flush=True)
            return None
        if r.status_code == 429:
            # Back off and retry once after 2 seconds
            time.sleep(2.0)
            _rate_limit()
            r = _s.get(
                f"{_BASE}/search",
                params={"q": artist, "per_page": 10},
                headers=headers,
                timeout=10,
            )
            if r.status_code == 429:
                print(f"[genius] 429 Rate limited for '{artist}' (after retry)", flush=True)
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

        # Rate limit before second API call
        _rate_limit()

        # Get full artist object with social links
        r2 = _s.get(
            f"{_BASE}/artists/{artist_id}",
            params={"text_format": "plain"},
            headers=headers,
            timeout=10,
        )
        if r2.status_code == 429:
            time.sleep(2.0)
            _rate_limit()
            r2 = _s.get(
                f"{_BASE}/artists/{artist_id}",
                params={"text_format": "plain"},
                headers=headers,
                timeout=10,
            )
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
        website = artist_data.get("url") or ""
        # Genius "url" is the genius.com page — we want the artist's own website
        # The actual website is in "custom_header_image_url" or header fields
        # But the REAL website link is in "description_annotation" or not exposed.
        # However, some artists have a dedicated website in their profile header.
        # The best we can get from the API is the artist's Genius page URL.
        # For actual artist websites, we check alternate_names or bio links.
        # Actually — Genius exposes artist websites via the artist page HTML, not API.
        # We'll use the Genius page URL as a fallback identifier.

        if ig:
            socials["instagram"] = ig.strip().lstrip("@")
        if tw:
            socials["twitter"] = tw.strip().lstrip("@")
        if fb:
            socials["facebook"] = fb.strip()

        # Check for artist website — Genius doesn't have a direct field,
        # but we can derive from the artist's header/image URLs or use
        # the associated label/distributor website from Chartmetric data.
        # For now, store the Genius profile URL for reference.
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
