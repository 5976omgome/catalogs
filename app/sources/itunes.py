"""iTunes Search API. No auth, no key. Pulls each artist's albums and
parses the copyright (P-line) into individual owners + any licensee.
Uses a shared, pooled requests.Session to avoid the [Errno 24] file-
descriptor leak that crashes long runs on macOS.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .. import cache, config, labels
from . import _http

_BASE = "https://itunes.apple.com"


def _session():
    return _http.session("itunes")


def _strip_year_glyph(text: str) -> str:
    """Strips '℗ 2024' / '(P) 2024' / '© 2024' year prefixes."""
    if not text:
        return ""
    s = text.strip()
    # Apple sometimes prepends a marketing line: "A Warner Records UK Release., ℗ 2026 PinkPantheress"
    # Split on the ℗ glyph if present and keep BOTH halves so the marketing
    # line gets evaluated as a separate owner.
    parts = re.split(r"[℗\u2117]|\(P\)|©", s)
    chunks = []
    for p in parts:
        p = p.strip(" ,;.")
        if not p:
            continue
        # strip a leading 4-digit year
        p = re.sub(r"^\s*\d{4}\s+", "", p).strip()
        if p:
            chunks.append(p)
    return " ; ".join(chunks)


def _parse_pline(pline: str) -> Dict[str, object]:
    """Returns {'owners': [...], 'licensee': str|None, 'raw': str}."""
    if not pline:
        return {"owners": [], "licensee": None, "raw": ""}
    cleaned = _strip_year_glyph(pline)
    licensee = labels.find_licensing_clause(pline)
    owners = labels.split_owners(cleaned)
    return {"owners": owners, "licensee": licensee, "raw": pline}


def _name_match(query: str, candidate: str) -> bool:
    q = labels.normalize(query)
    c = labels.normalize(candidate)
    if not q or not c:
        return False
    return q == c or (" " + q + " " in " " + c + " ")


def get_releases(artist: str, limit: int = 8) -> List[Dict[str, object]]:
    """Returns up to `limit` releases for `artist`, each a dict with
    keys: collectionName, releaseDate (year int or None), copyright (raw),
    owners (list[str]), licensee (str|None)."""
    if not artist:
        return []
    cached = cache.get("itunes", artist)
    if cached is not None:
        return cached
    s = _session()
    try:
        r = s.get(
            f"{_BASE}/search",
            params={
                "term": artist,
                "entity": "album",
                "limit": str(limit * 2),
                "country": "US",
            },
            timeout=config.HTTP_TIMEOUT,
        )
        if r.status_code != 200:
            cache.put("itunes", artist, [])
            return []
        results = r.json().get("results", []) or []
    except Exception:
        return []
    out: List[Dict[str, object]] = []
    seen = set()
    for it in results:
        if not _name_match(artist, it.get("artistName", "")):
            continue
        coll = (it.get("collectionName") or "").strip()
        if not coll or coll in seen:
            continue
        seen.add(coll)
        rel = (it.get("releaseDate") or "")[:4]
        try:
            year = int(rel) if rel.isdigit() else None
        except Exception:
            year = None
        parsed = _parse_pline(it.get("copyright") or "")
        out.append({
            "collectionName": coll,
            "releaseDate": year,
            "copyright": it.get("copyright") or "",
            "owners": parsed["owners"],
            "licensee": parsed["licensee"],
        })
        if len(out) >= limit:
            break
    cache.put("itunes", artist, out)
    return out


def get_earliest_year(artist: str) -> Optional[int]:
    rels = get_releases(artist, limit=20)
    years = [r.get("releaseDate") for r in rels if r.get("releaseDate")]
    return min(years) if years else None
