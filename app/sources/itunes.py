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


# Tokens that mark the end of one owner entity. When we see one of these
# immediately before a separator (and / & / /), it's much more likely to be
# a real joint-imprint boundary than part of a single artist name like
# "Iron and Wine" or "Tegan and Sara".
_ENTITY_TERMINATOR_RE = re.compile(
    r"\b("
    r"records?|recordings?|recording|productions?|production|"
    r"music|musik|musique|musica|"
    r"entertainment|ent\.?|"
    r"ltd\.?|llc\.?|inc\.?|gmbh|s\.?a\.?|"
    r"company|co\.?|"
    r"label|labels|group|publishing|rights"
    r")\s*$",
    re.IGNORECASE,
)

# A bracketed annotation like '[dist. Tratore]' or '(distributed by X)'
# indicates a distributor relationship for the preceding owner. We pull
# these out as a separate source so the rule engine sees the distributor.
_BRACKET_ANNOTATION_RE = re.compile(r"\s*\[\s*([^\]]+?)\s*\]\s*$")


def _split_safely(text: str) -> List[str]:
    """
    Split a single owner string into multiple entities only when the boundary
    is unambiguous:

    * '/' always splits (Apple uses it for joint imprints).
    * ',' splits ONLY when followed by ' ' and the right side starts with
      a capital letter and the left side ends in an entity terminator.
    * ' and ' / ' & ' split ONLY when the LEFT side ends in an entity
      terminator like "Records" / "Music" / "Productions" / etc.

    Without the terminator guard we'd shred artist names like "Iron and
    Wine" into ["Iron", "Wine"], "Lulu and mathumela band" into ["Lulu",
    "mathumela band"], etc. That was the source of the false-flag pattern
    the user reported (P-line matches artist exactly, but a fragment of
    the split fails the variant check).
    """
    if not text:
        return []

    parts: List[str] = []
    # First split on '/' which is unambiguous in Apple P-lines.
    for slash_chunk in re.split(r"\s*/\s*", text):
        slash_chunk = slash_chunk.strip()
        if not slash_chunk:
            continue
        # Now sub-split on ' and ' / ' & ' but only at safe boundaries.
        sub_parts = _split_at_terminator_boundary(slash_chunk)
        parts.extend(sub_parts)

    return [p.strip(" ,.;-") for p in parts if p.strip()]


def _split_at_terminator_boundary(s: str) -> List[str]:
    """
    Split on ' and ' / ' & ' only when the left side ends with an entity
    terminator. Otherwise the separator is part of the entity name and we
    keep the string whole.
    """
    # Find every separator candidate, decide for each whether it's a real
    # boundary based on whether the left side ends with a terminator.
    pattern = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)
    pieces = []
    last_end = 0
    for m in pattern.finditer(s):
        left = s[last_end:m.start()]
        if _ENTITY_TERMINATOR_RE.search(left):
            pieces.append(left)
            last_end = m.end()
    pieces.append(s[last_end:])
    return [p.strip() for p in pieces if p.strip()]


def _extract_owners(copyright_text: str) -> Tuple[List[str], str, str]:
    """
    Returns (owners, licensee, raw_pline).

    Owners are extracted from the P-line with the goal of NOT shredding a
    multi-word artist name. We split aggressively on '/' (Apple's joint-
    imprint separator) and conservatively on ' and ' / ' & ' / ',' — only
    when the left side looks like a complete entity (ends in Records /
    Music / Productions / etc.).

    Bracketed annotations like '[dist. Tratore]' are pulled out and added
    as a separate owner so the rule engine sees the distributor.
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
        prefix_clean = re.sub(r"\s+(Release|Records?\s+Release|Recording)\.?$", "", prefix_clean, flags=re.IGNORECASE)
        prefix_clean = prefix_clean.strip(" .,;")
        if prefix_clean:
            extra_owners.append(prefix_clean.strip())
        main = rest
    else:
        # Strip ℗/© and year in all common formats:
        #   ℗ 2024 Artist         (standard)
        #   ℗2024 Artist          (no space after glyph)
        #   ℗ (2024) Artist       (parenthesized year)
        #   ℗(2024) Artist        (parenthesized, no space)
        #   ℗ 2024 - Artist       (dash separator after year)
        #   ℗ 2024- Artist        (dash attached to year)
        #   (P) 2024 Artist       (ASCII fallback for ℗)
        #   (C) 2024 Artist       (ASCII fallback for ©)
        #   ℗ Esta compilación (P) 2024 Sony   (Spanish pattern)
        # Order matters: try the most specific patterns first.
        # Pattern: leading text like "Esta compilación (P) YYYY" or "This Compilation ℗ YYYY"
        main = re.sub(
            r"^.*?(?:esta\s+compilaci[oó]n|this\s+compilation)\s*(?:\(P\)|\(C\)|[℗©])\s*\(?\d{4}\)?\s*[-–—]?\s*",
            "", main, flags=re.IGNORECASE
        ).strip() or main
        # Pattern: (P) YYYY or (C) YYYY at the start
        main = re.sub(r"^\s*\([PCpc]\)\s*\(?\d{4}\)?\s*[-–—]?\s*", "", main).strip() or main
        # Pattern: ℗/© optionally followed by space, optionally parenthesized year, optional dash
        main = re.sub(r"[℗©]\s*\(?\d{4}\)?\s*[-–—]?\s*", "", main).strip()

    # Strip Spanish "bajo" (= "under") prefix on remaining text
    main = re.sub(r"^\s*bajo\s+", "", main, flags=re.IGNORECASE)

    # Pull out '[dist. X]' / '[distributed by X]' annotations and treat them
    # as a separate owner so the rule engine sees the distributor.
    annotation_owners: List[str] = []
    for _ in range(3):  # at most a few annotations
        m = _BRACKET_ANNOTATION_RE.search(main)
        if not m:
            break
        annotation = m.group(1).strip()
        # Strip 'dist.' / 'distributed by' / 'mfd by' / 'mfd. by' prefixes.
        cleaned = re.sub(
            r"^(dist\.?\s*by|distributed\s+by|dist\.?|distributed|"
            r"mfd\.?\s*by|mfd\.?|manufactured\s+and\s+distributed\s+by)\s+",
            "",
            annotation,
            flags=re.IGNORECASE,
        ).strip()
        if cleaned:
            annotation_owners.append(cleaned)
        main = main[: m.start()].rstrip(" ,.;-")

    # Conservative split on ',', ' and ', ' & ', '/'
    parts = _split_safely(main)

    owners = extra_owners + parts + annotation_owners
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
