"""Genius API — social media profiles for artists.

Uses the Client Access Token (read-only, no user OAuth needed).
Returns Instagram, Facebook, YouTube, and Website URLs.

Flow:
  1. GET /search?q=<artist> → find the artist ID with strict name matching
  2. GET /artists/:id → pull social_links object

Rate: No documented rate limit, but we add polite delays.
Auth: Bearer token in Authorization header.
"""
from __future__ import annotations

import re
import time
from typing import Dict, Optional

import requests

from .. import cache, config
from ..labels import normalize

BASE = "https://api.genius.com"


def _headers() -> dict:
    """Build auth headers. Token read live so Settings saves take effect immediately."""
    token = config.genius_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _get(url: str, params: dict = None, timeout: int = 10) -> Optional[dict]:
    """Make authenticated GET. Returns None on any failure."""
    headers = _headers()
    if not headers:
        return None
    try:
        r = requests.get(url, params=params or {}, headers=headers, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _find_artist_id(artist_name: str) -> Optional[int]:
    """
    Search Genius for the artist. Returns their Genius artist ID only if
    the name matches strictly (normalized exact match or substring containment).
    This prevents returning the wrong artist's socials for common names.
    """
    key = f"genius:aid:{normalize(artist_name)}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    data = _get(f"{BASE}/search", {"q": artist_name})
    if not data:
        cache.set_(key, None)
        return None

    hits = data.get("response", {}).get("hits", [])
    target = normalize(artist_name)

    # Pass 1: exact normalized match on primary_artist name
    for hit in hits:
        primary = hit.get("result", {}).get("primary_artist", {})
        if normalize(primary.get("name", "")) == target:
            aid = primary.get("id")
            cache.set_(key, aid)
            return aid

    # Pass 2: substring containment (catches slight variations)
    for hit in hits:
        primary = hit.get("result", {}).get("primary_artist", {})
        pn = normalize(primary.get("name", ""))
        if target and pn and (target in pn or pn in target):
            aid = primary.get("id")
            cache.set_(key, aid)
            return aid

    # No confident match — don't return wrong artist's socials
    cache.set_(key, None)
    return None


def get_socials(artist_name: str) -> Dict[str, str]:
    """
    Main entry point. Returns a dict with social media URLs:
    {
        "instagram": "https://instagram.com/handle" or "",
        "facebook": "https://facebook.com/handle" or "",
        "youtube": "https://youtube.com/..." or "",
        "website": "https://..." or "",
    }

    Returns all empty strings if the artist isn't found or has no socials.
    """
    if not config.genius_token():
        return {"instagram": "", "facebook": "", "youtube": "", "website": ""}

    key = f"genius:socials:{normalize(artist_name)}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    aid = _find_artist_id(artist_name)
    if not aid:
        result = {"instagram": "", "facebook": "", "youtube": "", "website": ""}
        cache.set_(key, result)
        return result

    time.sleep(0.15)  # polite delay between search and detail

    data = _get(f"{BASE}/artists/{aid}")
    if not data:
        result = {"instagram": "", "facebook": "", "youtube": "", "website": ""}
        cache.set_(key, result)
        return result

    artist = data.get("response", {}).get("artist", {})

    # Primary fields (handles only — we build the full URL)
    ig_handle = (artist.get("instagram_name") or "").strip()
    fb_handle = (artist.get("facebook_name") or "").strip()

    # social_links object has full URLs for YouTube and website
    social_links = artist.get("social_links") or {}
    youtube = (social_links.get("youtube") or "").strip()
    website = (social_links.get("website") or "").strip()

    result = {
        "instagram": f"https://instagram.com/{ig_handle}" if ig_handle else "",
        "facebook": f"https://facebook.com/{fb_handle}" if fb_handle else "",
        "youtube": youtube,
        "website": website,
    }

    cache.set_(key, result)
    return result
