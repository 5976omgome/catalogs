"""Discogs client.

Auth: personal access token in Authorization header.
Rate limit: 60 req/min unauthenticated, more with token.
We filter to main-artist releases only and skip compilations / "appears on"
credits, since those are misleading for ownership questions.
"""
from __future__ import annotations

from typing import Iterable

from .. import cache
from ..config import DISCOGS_TOKEN, TOP_N_RELEASES, USER_AGENT
from ..http import get_json, polite_sleep
from ..labels import normalize

BASE = "https://api.discogs.com"
SOURCE = "discogs"


def _headers() -> dict:
    h = {"User-Agent": USER_AGENT, "Accept": "application/vnd.discogs.v2.discogs+json"}
    if DISCOGS_TOKEN:
        h["Authorization"] = f"Discogs token={DISCOGS_TOKEN}"
    return h


def is_configured() -> bool:
    return bool(DISCOGS_TOKEN)


def _find_artist_id(artist_name: str) -> int | None:
    data = get_json(
        f"{BASE}/database/search",
        params={"q": artist_name, "type": "artist", "per_page": 5},
        headers=_headers(),
    )
    if not data:
        return None
    results = data.get("results", []) or []
    if not results:
        return None
    target = normalize(artist_name)
    for res in results:
        if normalize(res.get("title", "")) == target:
            return res.get("id")
    return results[0].get("id")


def _artist_releases(artist_id: int, per_page: int = 25) -> list[dict]:
    data = get_json(
        f"{BASE}/artists/{artist_id}/releases",
        params={"per_page": per_page, "sort": "year", "sort_order": "desc"},
        headers=_headers(),
    )
    return (data or {}).get("releases", []) or []


def get_releases(artist_name: str, top_n: int = TOP_N_RELEASES) -> list[dict]:
    """Return up to top_n recent main-artist releases as dicts:
        {title, label, year, release_id}
    """
    cached = cache.get(SOURCE, f"{artist_name}|{top_n}")
    if cached is not None:
        return cached

    if not is_configured():
        return []

    artist_id = _find_artist_id(artist_name)
    if not artist_id:
        cache.put(SOURCE, f"{artist_name}|{top_n}", [])
        return []

    polite_sleep(0.6)
    releases = _artist_releases(artist_id, per_page=25)

    out: list[dict] = []
    seen_labels: set[str] = set()
    for rel in releases:
        if len(out) >= top_n:
            break
        # Only main-artist releases; skip "Appears On" / TrackAppearance.
        role = (rel.get("role") or "").lower()
        if role and role not in ("main", "release"):
            continue
        # Skip compilations / various artists style entries
        rtype = (rel.get("type") or "").lower()
        if rtype not in ("master", "release"):
            continue

        label = (rel.get("label") or "").strip()
        if not label or label.lower() in ("not on label", "[no label]"):
            continue
        # De-dup by label so we get up to N distinct labels
        if label in seen_labels:
            continue
        seen_labels.add(label)
        out.append({
            "title": rel.get("title", ""),
            "label": label,
            "year": rel.get("year", ""),
            "release_id": rel.get("id"),
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
