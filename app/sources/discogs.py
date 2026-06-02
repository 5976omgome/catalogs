"""Discogs API - free token, returns historical label data.

Reads the Discogs token live (per call) so a Save in the Settings UI
takes effect immediately, without restarting the server.
"""
import re
import time
from typing import List

import requests

from .. import cache, config
from ..config import USER_AGENT
from ..labels import normalize

BASE = "https://api.discogs.com"


def _headers():
    h = {"User-Agent": USER_AGENT}
    token = config.discogs_token()
    if token:
        h["Authorization"] = f"Discogs token={token}"
    return h


def _get(url: str, params: dict = None, timeout: int = 10):
    r = requests.get(url, params=params or {}, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def _find_artist_id_strict(artist_name: str):
    """
    Find Discogs artist ID. Exact normalized match first, then loose
    token-overlap fallback for non-ASCII/diacritics differences.
    """
    try:
        data = _get(f"{BASE}/database/search", {
            "q": artist_name, "type": "artist", "per_page": 10,
        })
    except Exception:
        return None
    an = normalize(artist_name)
    # Pass 1: exact
    for r in data.get("results", []):
        if normalize(r.get("title", "")) == an:
            return r.get("id")
    # Pass 2: loose token-overlap (same logic as Deezer)
    if len(artist_name) >= 4:
        an_words = set(re.findall(r"[a-z0-9]{2,}", an))
        for r in data.get("results", []):
            dn = normalize(r.get("title", ""))
            dn_words = set(re.findall(r"[a-z0-9]{2,}", dn))
            if not dn_words or not an_words:
                continue
            overlap = an_words & dn_words
            if len(overlap) >= max(1, len(an_words) * 0.6) and len(overlap) >= max(1, len(dn_words) * 0.6):
                return r.get("id")
    return None


def get_releases(artist_name: str, limit: int = 3) -> List[dict]:
    """Returns up to N main-artist releases sorted year desc. Each: {title, label, release_year}."""
    if not config.discogs_token():
        return []

    key = f"discogs:rel:{normalize(artist_name)}:{limit}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    artist_id = _find_artist_id_strict(artist_name)
    if not artist_id:
        cache.set_(key, [])
        return []

    time.sleep(0.4)
    try:
        data = _get(f"{BASE}/artists/{artist_id}/releases", {
            "per_page": 25, "sort": "year", "sort_order": "desc",
        })
    except Exception:
        cache.set_(key, [])
        return []

    out = []
    seen_ids = set()
    for rel in data.get("releases", []):
        if len(out) >= limit:
            break
        role = (rel.get("role") or "").lower()
        # Skip "Appearance" and other side credits
        if role and role not in ("main", ""):
            continue
        rid = rel.get("id")
        if not rid or rid in seen_ids:
            continue
        seen_ids.add(rid)
        label = (rel.get("label") or "").strip()
        if label.lower() in ("not on label", "[no label]", "none", ""):
            label = ""
        year = str(rel.get("year") or "")
        out.append({
            "title": rel.get("title", ""),
            "label": label,
            "release_year": year if year and year != "0" else "",
        })

    cache.set_(key, out)
    return out


def get_earliest_year(artist_name: str) -> str:
    """Earliest release year on Discogs (strict name match only)."""
    if not config.discogs_token():
        return ""
    key = f"discogs:earliest:{normalize(artist_name)}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    artist_id = _find_artist_id_strict(artist_name)
    if not artist_id:
        cache.set_(key, "")
        return ""

    time.sleep(0.4)
    try:
        data = _get(f"{BASE}/artists/{artist_id}/releases", {
            "per_page": 100, "sort": "year", "sort_order": "asc",
        })
    except Exception:
        cache.set_(key, "")
        return ""

    years = []
    for rel in data.get("releases", []):
        role = (rel.get("role") or "").lower()
        if role and role not in ("main", ""):
            continue
        y = rel.get("year")
        if y and isinstance(y, int) and y > 1900:
            years.append(str(y))
    out = min(years) if years else ""
    cache.set_(key, out)
    return out
