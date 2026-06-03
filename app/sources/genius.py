"""Genius API — pulls artist social media links.

Requires a free Client Access Token from https://genius.com/api-clients
Returns: instagram, twitter, facebook handles when available.
Uses shared Session for FD safety.
"""
import re
import time
from typing import Optional, Dict

from app.sources._http import ai_session as _s  # Reuse AI session (low traffic)
from app import config, cache

_BASE = "https://api.genius.com"


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower()) if s else ""


def get_socials(artist: str) -> Optional[Dict[str, str]]:
    """Fetch social media handles for an artist from Genius.

    Returns dict like:
        {"instagram": "handle", "twitter": "handle", "facebook": "handle"}
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
        # Search for artist
        r = _s.get(f"{_BASE}/search", params={"q": artist}, headers=headers, timeout=10)
        r.raise_for_status()
        hits = r.json().get("response", {}).get("hits", [])

        # Find the artist ID from search results
        an = _normalize(artist)
        artist_id = None
        for hit in hits:
            result = hit.get("result", {})
            primary = result.get("primary_artist", {})
            if primary:
                name = _normalize(primary.get("name", ""))
                if name == an or an in name or name in an:
                    artist_id = primary.get("id")
                    break

        if not artist_id:
            cache.put(cache_key, {})
            return None

        time.sleep(0.1)  # Be polite

        # Get full artist object with social links
        r2 = _s.get(f"{_BASE}/artists/{artist_id}", headers=headers, timeout=10)
        r2.raise_for_status()
        artist_data = r2.json().get("response", {}).get("artist", {})

        socials = {}
        ig = artist_data.get("instagram_name", "")
        tw = artist_data.get("twitter_name", "")
        fb = artist_data.get("facebook_name", "")

        if ig:
            socials["instagram"] = ig
        if tw:
            socials["twitter"] = tw
        if fb:
            socials["facebook"] = fb

        cache.put(cache_key, socials if socials else {})
        return socials if socials else None

    except Exception:
        return None
