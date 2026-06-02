"""Deezer API - free, no auth. Returns label per album."""
import re
import time
from typing import List

import requests

from .. import cache
from ..config import USER_AGENT
from ..labels import normalize

BASE = "https://api.deezer.com"
HEADERS = {"User-Agent": USER_AGENT}


def _get(url: str, params: dict = None, timeout: int = 10):
    r = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _find_artist_id_strict(artist_name: str):
    """
    Find the Deezer artist ID. Tries exact normalized match first, then
    falls back to a looser token-overlap match to handle non-English names,
    diacritics, and minor spelling differences between Chartmetric and Deezer.
    """
    try:
        data = _get(f"{BASE}/search/artist", {"q": artist_name, "limit": 10})
    except Exception:
        return None
    an = normalize(artist_name)
    # Pass 1: exact normalized match
    for a in data.get("data", []):
        if normalize(a.get("name", "")) == an:
            return a.get("id")
    # Pass 2: loose match — at least 60% token overlap in both directions.
    # This catches cases like "Hélio Ziskind" vs "Helio Ziskind" or
    # "Křesťanská" vs "Krestanska" after diacritics are stripped.
    an_tokens = set(an)  # character-level for short names
    if len(artist_name) >= 4:
        an_words = set(re.findall(r"[a-z0-9]{2,}", an))
        for a in data.get("data", []):
            dn = normalize(a.get("name", ""))
            dn_words = set(re.findall(r"[a-z0-9]{2,}", dn))
            if not dn_words or not an_words:
                continue
            # Both directions: how much of artist is in deezer, and vice versa
            overlap = an_words & dn_words
            if len(overlap) >= max(1, len(an_words) * 0.6) and len(overlap) >= max(1, len(dn_words) * 0.6):
                return a.get("id")
    return None


def get_releases(artist_name: str, limit: int = 3) -> List[dict]:
    """Returns up to N most recent releases. Each: {title, label, release_year}."""
    key = f"deezer:rel:{normalize(artist_name)}:{limit}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    artist_id = _find_artist_id_strict(artist_name)
    if not artist_id:
        cache.set_(key, [])
        return []

    try:
        data = _get(f"{BASE}/artist/{artist_id}/albums", {"limit": 20})
    except Exception:
        cache.set_(key, [])
        return []

    albums = data.get("data", [])
    # Sort by release_date desc if present
    def _date(a):
        return a.get("release_date", "") or ""
    albums.sort(key=_date, reverse=True)

    out = []
    seen_ids = set()
    for a in albums:
        if len(out) >= limit:
            break
        aid = a.get("id")
        if not aid or aid in seen_ids:
            continue
        seen_ids.add(aid)
        # Fetch full album for label field
        time.sleep(0.1)
        try:
            full = _get(f"{BASE}/album/{aid}")
        except Exception:
            continue
        label = (full.get("label") or "").strip()
        if label.lower() in ("none", "[no label]", "no label"):
            label = ""
        rd = full.get("release_date", "")
        year = rd[:4] if rd and len(rd) >= 4 else ""
        out.append({
            "title": full.get("title", ""),
            "label": label,
            "release_year": year,
        })

    cache.set_(key, out)
    return out


def get_earliest_year(artist_name: str) -> str:
    """Earliest release year on Deezer (strict name match only)."""
    key = f"deezer:earliest:{normalize(artist_name)}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    artist_id = _find_artist_id_strict(artist_name)
    if not artist_id:
        cache.set_(key, "")
        return ""

    try:
        data = _get(f"{BASE}/artist/{artist_id}/albums", {"limit": 100})
    except Exception:
        cache.set_(key, "")
        return ""

    years = []
    for a in data.get("data", []):
        rd = a.get("release_date", "")
        if rd and len(rd) >= 4 and rd[:4].isdigit():
            years.append(rd[:4])
    out = min(years) if years else ""
    cache.set_(key, out)
    return out
