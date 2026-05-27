"""Deezer API. No auth required. Pulls the artist's most-recent albums
and reads the album.label field. Uses a shared pooled Session.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from .. import cache, config, labels
from . import _http

_BASE = "https://api.deezer.com"


def _session():
    return _http.session("deezer")


def _find_artist_id(name: str) -> Optional[int]:
    s = _session()
    try:
        r = s.get(
            f"{_BASE}/search/artist",
            params={"q": name, "limit": "5"},
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json().get("data", []) or []
    except Exception:
        return None
    target = labels.normalize(name)
    for hit in data:
        if labels.normalize(hit.get("name", "")) == target:
            return int(hit.get("id"))
    if data:
        # fallback: first result if its name is at least loosely a match
        first = data[0]
        if target in labels.normalize(first.get("name", "")):
            return int(first.get("id"))
    return None


def get_releases(artist: str, limit: int = 5) -> List[Dict[str, object]]:
    """Returns most-recent N releases as dicts with keys:
    title, releaseDate (year int or None), label (str)."""
    if not artist:
        return []
    cached = cache.get("deezer", artist)
    if cached is not None:
        return cached
    aid = _find_artist_id(artist)
    if aid is None:
        cache.put("deezer", artist, [])
        return []
    s = _session()
    try:
        r = s.get(
            f"{_BASE}/artist/{aid}/albums",
            params={"limit": str(limit * 2)},
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            cache.put("deezer", artist, [])
            return []
        albums = r.json().get("data", []) or []
    except Exception:
        return []
    out: List[Dict[str, object]] = []
    for alb in albums[:limit]:
        alb_id = alb.get("id")
        if not alb_id:
            continue
        try:
            time.sleep(0.05)
            ar = s.get(f"{_BASE}/album/{alb_id}", timeout=config.HTTP_TIMEOUT)
            if ar.status_code != 200:
                continue
            full = ar.json()
        except Exception:
            continue
        rel = (full.get("release_date") or "")[:4]
        try:
            year = int(rel) if rel.isdigit() else None
        except Exception:
            year = None
        out.append({
            "title": full.get("title", ""),
            "releaseDate": year,
            "label": (full.get("label") or "").strip(),
        })
    cache.put("deezer", artist, out)
    return out


def get_earliest_year(artist: str) -> Optional[int]:
    rels = get_releases(artist, limit=20)
    years = [r.get("releaseDate") for r in rels if r.get("releaseDate")]
    return min(years) if years else None
