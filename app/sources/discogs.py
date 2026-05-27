"""Discogs API. Reads token live from the keys store so a UI save takes
effect immediately. Uses a shared pooled Session.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .. import cache, config, labels
from . import _http

_BASE = "https://api.discogs.com"


def _session():
    return _http.session("discogs")


def _headers() -> Dict[str, str]:
    h = {"User-Agent": config.DISCOGS_USER_AGENT}
    tok = config.discogs_token()
    if tok:
        h["Authorization"] = f"Discogs token={tok}"
    return h


def _find_artist_id(name: str) -> Optional[int]:
    s = _session()
    try:
        r = s.get(
            f"{_BASE}/database/search",
            params={"q": name, "type": "artist", "per_page": "5"},
            headers=_headers(),
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results", []) or []
    except Exception:
        return None
    target = labels.normalize(name)
    for res in results:
        if labels.normalize(res.get("title", "")) == target:
            return int(res.get("id"))
    return None  # strict: no fallback to first result (avoids namesakes)


def get_releases(artist: str, limit: int = 5) -> List[Dict[str, object]]:
    if not artist:
        return []
    cached = cache.get("discogs", artist)
    if cached is not None:
        return cached
    aid = _find_artist_id(artist)
    if aid is None:
        cache.put("discogs", artist, [])
        return []
    s = _session()
    try:
        r = s.get(
            f"{_BASE}/artists/{aid}/releases",
            params={"per_page": str(limit * 3), "sort": "year", "sort_order": "desc"},
            headers=_headers(),
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            cache.put("discogs", artist, [])
            return []
        releases = r.json().get("releases", []) or []
    except Exception:
        return []
    out: List[Dict[str, object]] = []
    for rel in releases:
        if rel.get("type") != "master" and rel.get("role") not in ("Main", "", None):
            continue
        label = (rel.get("label") or "").strip()
        if not label or label.lower() in ("not on label", "[no label]"):
            continue
        title = (rel.get("title") or "").strip()
        year = rel.get("year")
        try:
            year = int(year) if year else None
        except Exception:
            year = None
        out.append({"title": title, "releaseDate": year, "label": label})
        if len(out) >= limit:
            break
    cache.put("discogs", artist, out)
    return out


def get_earliest_year(artist: str) -> Optional[int]:
    rels = get_releases(artist, limit=30)
    years = [r.get("releaseDate") for r in rels if r.get("releaseDate")]
    return min(years) if years else None
