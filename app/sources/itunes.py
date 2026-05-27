"""Apple iTunes Search API - free, no auth, returns P-line in 'copyright' field."""
import re
import time
from typing import List, Tuple

import requests

from .. import cache
from ..config import USER_AGENT
from ..labels import normalize, find_licensee

BASE = "https://itunes.apple.com"
HEADERS = {"User-Agent": USER_AGENT}


def _get(url: str, params: dict, timeout: int = 10):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _strip_pline(copyright_text: str) -> str:
    """
    Apple's copyright field looks like:
      '℗ 2024 Some Label, under exclusive license to Big Label'
      'A Warner Records UK Release., ℗ 2026 PinkPantheress'
    Returns the meaningful text after stripping the year+glyph.
    """
    if not copyright_text:
        return ""
    s = copyright_text.strip()
    # Strip leading "A Foo Records UK Release., " style prefix - but keep it as a separate signal
    return s


def _extract_owners(copyright_text: str) -> Tuple[List[str], str, str]:
    """
    Returns (owners, licensee, raw_pline).
    Owners are split on '/', '&', and 'and' between recognizable entity names.
    """
    if not copyright_text:
        return [], "", ""
    raw = copyright_text.strip()

    # Find licensee via marker
    licensee = find_licensee(raw)

    # Cut off licensee phrase from main owner string
    main = raw
    if licensee:
        # find start of marker, cut there
        lower = main.lower()
        for marker in [
            "under exclusive licen", "under licen", "exclusive license to",
            "exclusive licence to", "licensed to", "licencia exclusiva",
            "bajo licencia", "sous licence", "in licenza", "unter lizenz",
            "onder licentie", "distributed by", "dist. by", "mfd by", "mfd. by",
        ]:
            idx = lower.find(marker)
            if idx >= 0:
                main = main[:idx].rstrip(" ,.;-")
                break

    # Strip leading marketing prefix like "A Warner Records UK Release.," then continue parsing
    # Example: "A Warner Records UK Release., ℗ 2026 PinkPantheress"
    extra_owners = []
    pre_glyph_match = re.match(r"^(.+?)[,;]\s*[℗©]\s*\d{4}\s*(.+)$", main)
    if pre_glyph_match:
        prefix = pre_glyph_match.group(1).strip()
        rest = pre_glyph_match.group(2).strip()
        # Strip leading "A " article and trailing words like "Release"
        prefix_clean = re.sub(r"^A\s+", "", prefix, flags=re.IGNORECASE)
        prefix_clean = re.sub(r"\s+(Release|Records Release|Recording)$", "", prefix_clean, flags=re.IGNORECASE)
        if prefix_clean:
            extra_owners.append(prefix_clean.strip())
        main = rest
    else:
        # Strip ℗/© and year
        main = re.sub(r"[℗©]\s*\d{4}\s*", "", main).strip()

    # Strip Spanish "bajo" (= "under") prefix on remaining text
    main = re.sub(r"^\s*bajo\s+", "", main, flags=re.IGNORECASE)

    # Split owners on /, &, and
    parts = re.split(r"\s*/\s*|\s+&\s+|\s+and\s+", main)
    parts = [p.strip(" ,.;-") for p in parts if p.strip()]

    owners = extra_owners + parts
    # Dedupe preserving order
    seen = set()
    out = []
    for o in owners:
        k = normalize(o)
        if k and k not in seen:
            seen.add(k)
            out.append(o)
    return out, licensee, raw


def get_releases(artist_name: str, limit: int = 5) -> List[dict]:
    """
    Returns list of {title, owners, licensee, pline, release_year}
    sorted by release date descending.
    """
    key = f"itunes:rel:{normalize(artist_name)}:{limit}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    try:
        data = _get(f"{BASE}/search", {
            "term": artist_name,
            "entity": "album",
            "limit": 25,
        })
    except Exception:
        return []

    results = data.get("results", [])
    an = normalize(artist_name)

    # Strict name match - only keep results where iTunes artistName matches
    matched = []
    for r in results:
        ra = normalize(r.get("artistName", ""))
        if ra == an or an in ra.split() or ra in an.split():
            matched.append(r)

    if not matched:
        cache.set_(key, [])
        return []

    # Sort by release date desc
    def _date(r):
        return r.get("releaseDate", "") or ""

    matched.sort(key=_date, reverse=True)

    out = []
    seen_titles = set()
    for r in matched:
        if len(out) >= limit:
            break
        title = r.get("collectionName", "")
        tnorm = normalize(title)
        if not title or tnorm in seen_titles:
            continue
        seen_titles.add(tnorm)
        copyright_text = r.get("copyright", "")
        owners, licensee, raw = _extract_owners(copyright_text)
        year = ""
        rd = r.get("releaseDate", "")
        if rd and len(rd) >= 4 and rd[:4].isdigit():
            year = rd[:4]
        out.append({
            "title": title,
            "owners": owners,
            "licensee": licensee,
            "pline": raw,
            "release_year": year,
        })
        time.sleep(0.05)

    cache.set_(key, out)
    return out


def get_earliest_year(artist_name: str) -> str:
    """Earliest release year on Apple Music for this artist (strict name match)."""
    key = f"itunes:earliest:{normalize(artist_name)}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    try:
        data = _get(f"{BASE}/search", {
            "term": artist_name,
            "entity": "album",
            "limit": 50,
        })
    except Exception:
        return ""

    an = normalize(artist_name)
    years = []
    for r in data.get("results", []):
        if normalize(r.get("artistName", "")) != an:
            continue
        rd = r.get("releaseDate", "")
        if rd and len(rd) >= 4 and rd[:4].isdigit():
            years.append(rd[:4])
    out = min(years) if years else ""
    cache.set_(key, out)
    return out
