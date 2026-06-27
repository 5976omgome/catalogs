"""Deezer API — pulls label data from album objects.

No auth required. Free. 50 requests / 5 seconds rate limit.
Uses shared Session for FD safety.
"""
import re
import time
from typing import List, Dict, Optional

from app.sources._http import deezer_session as _s
from app.sources._match import artist_matches
from app import cache

_BASE = "https://api.deezer.com"


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower()) if s else ""


def get_releases(artist: str, limit: int = 5) -> List[Dict]:
    """Fetch up to `limit` recent releases with label info from Deezer.

    Returns list of dicts: {title, label, year}
    """
    cache_key = f"deezer:{_normalize(artist)}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    results = []
    try:
        # Search for artist tracks using advanced search
        params = {
            "q": f'artist:"{artist}"',
            "limit": 15,
            "order": "TRACK_DESC",  # Newest first
            "strict": "on",
        }
        r = _s.get(f"{_BASE}/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])

        # If strict returns nothing, retry without
        if not data:
            params.pop("strict")
            r = _s.get(f"{_BASE}/search", params=params, timeout=10)
            r.raise_for_status()
            data = r.json().get("data", [])

        # Filter by artist name match (high-precision: exact / token-set
        # equality — loose substring matching removed to stop namesake bleed).
        matched = []
        for track in data:
            if artist_matches(artist, track.get("artist", {}).get("name", "")):
                matched.append(track)
            if len(matched) >= limit * 2:
                break

        # Get unique album IDs and fetch each for label
        seen_albums = set()
        for track in matched:
            if len(results) >= limit:
                break
            album_id = track.get("album", {}).get("id")
            if not album_id or album_id in seen_albums:
                continue
            seen_albums.add(album_id)

            time.sleep(0.12)  # Rate limit
            try:
                ra = _s.get(f"{_BASE}/album/{album_id}", timeout=10)
                ra.raise_for_status()
                album_data = ra.json()
                label = album_data.get("label", "").strip()
                title = album_data.get("title", "")
                year = None
                rd = album_data.get("release_date", "")
                if rd:
                    m = re.match(r"(\d{4})", rd)
                    if m:
                        year = int(m.group(1))

                if label and label.lower() not in ("", "none", "[no label]"):
                    results.append({
                        "title": title,
                        "label": label,
                        "year": year,
                    })
            except Exception:
                continue

    except Exception:
        pass

    cache.put(cache_key, results)
    return results


def get_earliest_year(artist: str) -> Optional[int]:
    """Get the earliest release year from Deezer for this artist."""
    cache_key = f"deezer_earliest:{_normalize(artist)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached[0] if cached else None

    try:
        # Search for artist ID first
        r = _s.get(f"{_BASE}/search/artist", params={
            "q": artist, "limit": 5, "strict": "on",
        }, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])

        artist_id = None
        for item in data:
            if artist_matches(artist, item.get("name", "")):
                artist_id = item.get("id")
                break
        # No loose fallback: an inexact Deezer artist is the wrong artist, and a
        # wrong earliest-year is worse than none (year is informational only).

        if not artist_id:
            cache.put(cache_key, [])
            return None

        time.sleep(0.12)
        # Get albums sorted by release date ascending
        r2 = _s.get(f"{_BASE}/artist/{artist_id}/albums", params={
            "limit": 50, "order": "RELEASE_DATE_ASC",
        }, timeout=10)
        r2.raise_for_status()
        albums = r2.json().get("data", [])

        years = []
        for album in albums:
            rd = album.get("release_date", "")
            if rd:
                m = re.match(r"(\d{4})", rd)
                if m:
                    years.append(int(m.group(1)))

        earliest = min(years) if years else None
        cache.put(cache_key, [earliest])
        return earliest

    except Exception:
        return None
