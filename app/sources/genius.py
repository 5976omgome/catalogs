"""Genius API — pulls artist social media links.

Requires a free Client Access Token from https://genius.com/api-clients
Returns: instagram, twitter, facebook handles when available.
Uses shared Session for FD safety.

NOTE: Genius does NOT provide YouTube URLs in artist data.
YouTube column is populated from other sources or left empty.
"""
import re
import time
from typing import Optional, Dict

from app.sources._http import ai_session as _s
from app import config, cache

_BASE = "https://api.genius.com"


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
            print(f"[genius] 429 Rate limited for '{artist}'", flush=True)
            return None
        r.raise_for_status()

        data = r.json()
        hits = data.get("response", {}).get("hits", [])

        if not hits:
            print(f"[genius] No search results for '{artist}'", flush=True)
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
                # Match: exact, substring in either direction
                if name == an or an in name or name in an:
                    artist_id = primary.get("id")
                    artist_match_name = primary.get("name", "")
                    break

        if not artist_id:
            # Try looser matching — first result's primary artist
            first_hit = hits[0].get("result", {}).get("primary_artist", {})
            if first_hit:
                first_name = _normalize(first_hit.get("name", ""))
                # Only use first result if names share significant overlap
                if len(an) >= 3 and (an[:3] in first_name or first_name[:3] in an):
                    artist_id = first_hit.get("id")
                    artist_match_name = first_hit.get("name", "")

        if not artist_id:
            print(f"[genius] No artist match for '{artist}' in {len(hits)} hits", flush=True)
            cache.put(cache_key, {})
            return None

        time.sleep(0.15)  # Be polite to rate limits

        # Get full artist object with social links
        # text_format=plain ensures all fields are returned
        r2 = _s.get(
            f"{_BASE}/artists/{artist_id}",
            params={"text_format": "plain"},
            headers=headers,
            timeout=10,
        )
        if r2.status_code != 200:
            print(f"[genius] Artist fetch failed ({r2.status_code}) for '{artist}' (id={artist_id})", flush=True)
            cache.put(cache_key, {})
            return None

        artist_data = r2.json().get("response", {}).get("artist", {})

        if not artist_data:
            print(f"[genius] Empty artist data for '{artist}' (id={artist_id})", flush=True)
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

        if socials:
            print(f"[genius] ✓ Found socials for '{artist}' → {list(socials.keys())}", flush=True)
        else:
            print(f"[genius] Artist '{artist}' found (matched: '{artist_match_name}') but no socials on profile", flush=True)

        cache.put(cache_key, socials if socials else {})
        return socials if socials else None

    except Exception as e:
        print(f"[genius] Error for '{artist}': {e}", flush=True)
        return None
