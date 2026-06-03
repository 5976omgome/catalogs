"""Discogs API — pulls label data from release history.

Requires a free personal access token. Strong on physical releases and
historical catalog data. Uses shared Session for FD safety.
"""
import re
import time
from typing import List, Dict, Optional

from app.sources._http import discogs_session as _s
from app import config, cache

_BASE = "https://api.discogs.com"
_UA = "CatalogAuditApp/2.0"


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower()) if s else ""


def _headers() -> dict:
    token = config.discogs_token()
    h = {"User-Agent": _UA}
    if token:
        h["Authorization"] = f"Discogs token={token}"
    return h


def get_releases(artist: str, limit: int = 5) -> List[Dict]:
    """Fetch up to `limit` releases with label data from Discogs.

    Returns list of dicts: {title, label, year}
    """
    token = config.discogs_token()
    if not token:
        return []

    cache_key = f"discogs:{_normalize(artist)}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    results = []
    try:
        # Search for artist
        r = _s.get(f"{_BASE}/database/search", params={
            "q": artist, "type": "artist", "per_page": 5,
        }, headers=_headers(), timeout=12)
        r.raise_for_status()
        search_results = r.json().get("results", [])

        # Find exact name match, fallback to first
        an = _normalize(artist)
        artist_id = None
        for res in search_results:
            if _normalize(res.get("title", "")) == an:
                artist_id = res.get("id")
                break
        if not artist_id and search_results:
            # Only use first result if it's reasonably close
            first_name = _normalize(search_results[0].get("title", ""))
            if an in first_name or first_name in an:
                artist_id = search_results[0].get("id")

        if not artist_id:
            cache.put(cache_key, [])
            return []

        time.sleep(0.5)  # Rate limit (Discogs is 60/min)

        # Get releases sorted newest first
        r2 = _s.get(f"{_BASE}/artists/{artist_id}/releases", params={
            "per_page": 20, "sort": "year", "sort_order": "desc",
        }, headers=_headers(), timeout=12)
        r2.raise_for_status()
        releases = r2.json().get("releases", [])

        seen_labels = set()
        for rel in releases:
            if len(results) >= limit:
                break

            # Skip non-main credits (compilations, features)
            role = rel.get("role", "").lower()
            if role and role not in ("main", ""):
                continue

            label = rel.get("label", "").strip()
            title = rel.get("title", "")
            year = rel.get("year")

            if not label or label.lower() in ("not on label", "[no label]", ""):
                continue

            # Dedupe by label name
            ln = label.lower()
            if ln in seen_labels:
                continue
            seen_labels.add(ln)

            results.append({
                "title": title,
                "label": label,
                "year": year,
            })

    except Exception:
        pass

    cache.put(cache_key, results)
    return results


def get_earliest_year(artist: str) -> Optional[int]:
    """Get earliest release year from Discogs."""
    token = config.discogs_token()
    if not token:
        return None

    cache_key = f"discogs_earliest:{_normalize(artist)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached[0] if cached else None

    try:
        r = _s.get(f"{_BASE}/database/search", params={
            "q": artist, "type": "artist", "per_page": 5,
        }, headers=_headers(), timeout=12)
        r.raise_for_status()
        search_results = r.json().get("results", [])

        an = _normalize(artist)
        artist_id = None
        for res in search_results:
            if _normalize(res.get("title", "")) == an:
                artist_id = res.get("id")
                break

        if not artist_id:
            cache.put(cache_key, [])
            return None

        time.sleep(0.5)
        r2 = _s.get(f"{_BASE}/artists/{artist_id}/releases", params={
            "per_page": 50, "sort": "year", "sort_order": "asc",
        }, headers=_headers(), timeout=12)
        r2.raise_for_status()
        releases = r2.json().get("releases", [])

        years = []
        for rel in releases:
            role = rel.get("role", "").lower()
            if role and role not in ("main", ""):
                continue
            y = rel.get("year")
            if y and isinstance(y, int) and y > 1900:
                years.append(y)

        earliest = min(years) if years else None
        cache.put(cache_key, [earliest])
        return earliest

    except Exception:
        return None
