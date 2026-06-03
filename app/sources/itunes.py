"""iTunes Search API — pulls P-lines (copyright field) from Apple Music.

No auth required. Free. Returns the actual legal phonographic copyright owner.
Pulls up to 15 most recent releases per artist.
"""
import re
import time
from typing import List, Dict, Optional

from app.sources._http import itunes_session as _s
from app import cache

_BASE = "https://itunes.apple.com"


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower()) if s else ""


def get_releases(artist: str, limit: int = 15) -> List[Dict]:
    """Fetch up to `limit` most recent albums for an artist from iTunes.

    Returns list of dicts: {title, label, year, copyright_raw}
    where `label` is the parsed primary owner from the copyright field.
    """
    cache_key = f"itunes:{_normalize(artist)}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    results = []
    try:
        # Search for the artist
        r = _s.get(f"{_BASE}/search", params={
            "term": artist,
            "entity": "album",
            "limit": 50,
            "media": "music",
        }, timeout=12)
        r.raise_for_status()
        data = r.json().get("results", [])

        # Filter to artist name match
        an = _normalize(artist)
        matched = []
        for item in data:
            item_artist = _normalize(item.get("artistName", ""))
            # Require strong match: normalized contains or equals
            if an == item_artist or an in item_artist or item_artist in an:
                matched.append(item)

        # Sort by release date descending (newest first)
        matched.sort(
            key=lambda x: x.get("releaseDate", ""),
            reverse=True,
        )

        # Take up to limit
        for item in matched[:limit]:
            copyright_raw = item.get("copyright", "").strip()
            title = item.get("collectionName", "")
            year = None
            rd = item.get("releaseDate", "")
            if rd:
                year_match = re.match(r"(\d{4})", rd)
                if year_match:
                    year = int(year_match.group(1))

            # Parse owner from the copyright field
            label = _parse_copyright_owner(copyright_raw)

            results.append({
                "title": title,
                "label": label,
                "year": year,
                "copyright_raw": copyright_raw,
            })

    except Exception:
        pass

    cache.put(cache_key, results)
    return results


def get_earliest_year(artist: str) -> Optional[int]:
    """Get the earliest release year for this artist on iTunes."""
    cache_key = f"itunes_earliest:{_normalize(artist)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached[0] if cached else None

    try:
        r = _s.get(f"{_BASE}/search", params={
            "term": artist,
            "entity": "album",
            "limit": 200,
            "media": "music",
        }, timeout=12)
        r.raise_for_status()
        data = r.json().get("results", [])

        an = _normalize(artist)
        years = []
        for item in data:
            item_artist = _normalize(item.get("artistName", ""))
            if an == item_artist or an in item_artist or item_artist in an:
                rd = item.get("releaseDate", "")
                if rd:
                    m = re.match(r"(\d{4})", rd)
                    if m:
                        years.append(int(m.group(1)))

        earliest = min(years) if years else None
        cache.put(cache_key, [earliest])
        return earliest
    except Exception:
        return None


def _parse_copyright_owner(copyright_text: str) -> str:
    """Extract the primary owner from a copyright/P-line string.

    Strips the ℗ YYYY prefix and returns the owner text.
    Handles Apple's format where marketing prefix comes before ℗.
    """
    if not copyright_text:
        return ""

    text = copyright_text.strip()

    # Handle: "A Warner Records UK Release., ℗ 2026 PinkPantheress"
    # The ℗ glyph may appear mid-string with a marketing prefix before it
    pline_idx = text.find("\u2117")  # ℗ character
    if pline_idx > 0:
        # Everything before ℗ is a marketing prefix — extract it too
        prefix = text[:pline_idx].strip(" ,;.")
        after_p = text[pline_idx:]
        # Strip "℗ YYYY " from the after part
        owner_after = re.sub(r"^[\u2117(P)]+\s*\d{4}\s*", "", after_p).strip()
        # If prefix contains a label name, include it
        if prefix and not prefix.lower().startswith("a ") and len(prefix) > 3:
            return f"{prefix}; {owner_after}" if owner_after else prefix
        return owner_after

    # Standard format: "℗ 2024 Label Name" or "(P) 2024 Label Name"
    text = re.sub(r"^[\u2117(P)]+\s*", "", text)
    text = re.sub(r"^\d{4}\s*", "", text)
    # Also handle "Esta compilacion (P) 2024 ..."
    text = re.sub(r"^Esta compilaci[oó]n\s*\(P\)\s*\d{4}\s*", "", text, flags=re.I)

    return text.strip(" ,;.")
