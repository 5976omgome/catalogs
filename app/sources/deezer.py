"""Deezer client.

Public API, no auth. Rate limit: 50 requests / 5 seconds.
We pull the artist's most RECENT releases (sorted newest first) so the
label data reflects current self-release status, not their most popular
old track.
"""
from __future__ import annotations

from typing import Iterable

from .. import cache
from ..config import TOP_N_RELEASES
from ..http import get_json, polite_sleep
from ..labels import normalize

BASE = "https://api.deezer.com"
SOURCE = "deezer"


def _name_matches(query: str, candidate: str) -> bool:
    a = normalize(query)
    b = normalize(candidate)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _find_artist_id(artist_name: str) -> int | None:
    data = get_json(
        f"{BASE}/search/artist",
        params={"q": artist_name, "limit": 5, "strict": "on"},
    ) or get_json(
        f"{BASE}/search/artist",
        params={"q": artist_name, "limit": 5},
    )
    if not data:
        return None
    for entry in data.get("data", []):
        if _name_matches(artist_name, entry.get("name", "")):
            return entry.get("id")
    # Fall back to first result if none matched exactly
    items = data.get("data", [])
    return items[0].get("id") if items else None


def _albums_for_artist(artist_id: int, limit: int = 25) -> list[dict]:
    data = get_json(
        f"{BASE}/artist/{artist_id}/albums",
        params={"limit": limit},
    )
    return (data or {}).get("data", []) or []


def _album_detail(album_id: int) -> dict | None:
    return get_json(f"{BASE}/album/{album_id}")


def get_releases(artist_name: str, top_n: int = TOP_N_RELEASES) -> list[dict]:
    """Return up to top_n recent releases as dicts:
        {title, label, release_date, album_id}

    Sorted newest first. Empty list if artist not found.
    """
    cached = cache.get(SOURCE, f"{artist_name}|{top_n}")
    if cached is not None:
        return cached

    artist_id = _find_artist_id(artist_name)
    if not artist_id:
        cache.put(SOURCE, f"{artist_name}|{top_n}", [])
        return []

    polite_sleep(0.12)
    albums = _albums_for_artist(artist_id, limit=25)
    # Sort newest first by release_date when present
    albums.sort(key=lambda a: a.get("release_date", "") or "", reverse=True)

    out: list[dict] = []
    seen_ids: set[int] = set()
    for album in albums:
        if len(out) >= top_n:
            break
        aid = album.get("id")
        if not aid or aid in seen_ids:
            continue
        seen_ids.add(aid)
        polite_sleep(0.12)
        detail = _album_detail(aid)
        if not detail:
            continue
        label = (detail.get("label") or "").strip()
        if label.lower() in ("none", "[no label]"):
            label = ""
        out.append({
            "title": detail.get("title", album.get("title", "")),
            "label": label,
            "release_date": detail.get("release_date", album.get("release_date", "")),
            "album_id": aid,
        })

    cache.put(SOURCE, f"{artist_name}|{top_n}", out)
    return out


def labels_only(releases: Iterable[dict]) -> list[str]:
    seen: list[str] = []
    for r in releases:
        lbl = (r.get("label") or "").strip()
        if lbl and lbl not in seen:
            seen.append(lbl)
    return seen
