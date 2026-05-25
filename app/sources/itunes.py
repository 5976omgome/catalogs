"""Apple iTunes Search API client.

This is the most authoritative free source we have access to:
the `copyright` field on each album result IS the literal P-line
that record labels deliver to all streaming services. It contains
the legal phonographic copyright owner, including any "under exclusive
licence to" or co-ownership clauses.

Endpoint: https://itunes.apple.com/search and /lookup
No auth required. No API key. No account. No premium.

Practical rate limit: ~20 requests/min per IP. We pace conservatively.
"""
from __future__ import annotations

import re
from typing import Iterable

from .. import cache
from ..config import TOP_N_RELEASES
from ..http import get_json, polite_sleep
from ..labels import normalize

BASE = "https://itunes.apple.com"
SOURCE = "itunes"

# Apple often prepends a marketing line before the ℗ glyph, e.g.
#   "A Warner Records UK Release., ℗ 2024 PinkPantheress"
# We extract that prefix as a separate "marketing entity" so it can be
# classified, then proceed with the ℗-side as the actual P-line body.
_MARKETING_BEFORE_PLINE = re.compile(
    r"^(?P<prefix>.+?)\s*[,.;:\s]+(?=℗|\(P\)|P\s+\d{4})",
    re.IGNORECASE,
)

# P-line text usually starts with one of these glyphs/strings.
# We leave them in the parsed result so it's clear we have the real P-line.
_PLINE_PREFIX = re.compile(r"^\s*(℗|\(P\)|P\s+)\s*", re.IGNORECASE)

# Substrings that indicate a licensing arrangement to a third party.
# These are red flags for catalog acquisition: even if the artist's own
# imprint is the primary owner, an "exclusive licence to X" means X
# controls the masters.
LICENSING_MARKERS: tuple[str, ...] = (
    "under exclusive licence to",
    "under exclusive license to",
    "under licence to",
    "under license to",
    "exclusively licenced to",
    "exclusively licensed to",
    "bajo licencia exclusiva para",
    "bajo licencia exclusiva a",
    "licencia exclusiva para",
    "licencia exclusiva a",
    "sous licence exclusive a",
    "sous licence exclusive à",
    "licence exclusive a",
    "licence exclusive à",
    "in licenza esclusiva a",
    "licenza esclusiva a",
    "lizenz exklusiv an",
    "in exclusieve licentie aan",
    "distribuido por",
    "distributed by",
    "marketed by",
    "manufactured by",
    "exclusive distribution by",
)

# Separators inside a P-line that split co-owners.
_CO_OWNER_SPLIT = re.compile(
    r"\s+(?:and|&|\+|/|,)\s+|\s*/\s*",
    re.IGNORECASE,
)


def _strip_year_and_glyph(pline: str) -> str:
    """Remove the leading P glyph and the 4-digit year so we can parse owners."""
    s = _PLINE_PREFIX.sub("", pline).strip()
    # leading 4-digit year, optionally followed by punctuation
    s = re.sub(r"^\d{4}[\s,.\-:]*", "", s).strip()
    return s


def parse_pline(pline: str) -> dict:
    """Break a P-line into structured pieces.

    Returns:
        {
          "raw": original P-line,
          "owners": [list of owner strings, primary first],
          "licensee": str or None  # who the masters are licensed TO, if any
        }
    """
    if not pline:
        return {"raw": "", "owners": [], "licensee": None}

    # Apple sometimes prefixes the ℗ block with a marketing release line
    # like "A Warner Records UK Release., ℗ 2024 PinkPantheress". The
    # marketing prefix is its own independent entity (it tells you who
    # released the thing for marketing purposes), so we capture it as
    # an additional owner BEFORE we strip the glyph.
    text = pline.strip()
    extra_owners: list[str] = []
    m = _MARKETING_BEFORE_PLINE.match(text)
    if m:
        prefix = m.group("prefix").strip(" .,;:")
        if prefix:
            extra_owners.append(prefix)
        text = text[m.end():].strip()

    body = _strip_year_and_glyph(text)

    # Detect a licensing handoff: "<owner> under exclusive licence to <licensee>"
    licensee: str | None = None
    lower = body.lower()
    for marker in LICENSING_MARKERS:
        idx = lower.find(marker)
        if idx != -1:
            licensee = body[idx + len(marker):].strip(" .,;:")
            body = body[:idx].strip(" .,;:")
            break

    owners_raw = _CO_OWNER_SPLIT.split(body) if body else []
    owners = [o.strip(" .,;:") for o in owners_raw if o and o.strip(" .,;:")]
    # Marketing prefix (if any) goes first in the owners list so it is
    # checked first by the rule engine.
    owners = extra_owners + owners

    return {"raw": pline.strip(), "owners": owners, "licensee": licensee}


def _name_matches(query: str, candidate: str) -> bool:
    a = normalize(query)
    b = normalize(candidate)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _search_albums(artist_name: str, limit: int = 25, country: str = "US") -> list[dict]:
    return (get_json(
        f"{BASE}/search",
        params={
            "term": artist_name,
            "entity": "album",
            "limit": limit,
            "country": country,
            "media": "music",
        },
    ) or {}).get("results", []) or []


def get_releases(artist_name: str, top_n: int = TOP_N_RELEASES,
                 country: str = "US") -> list[dict]:
    """Return up to top_n recent releases as dicts:
        {title, label, copyright, owners, licensee, release_date, album_id}

    'label' here is the parsed primary owner from the P-line, which is
    almost always more accurate than any standalone "label" field on
    other APIs.
    """
    cache_key = f"{artist_name}|{top_n}|{country}"
    cached = cache.get(SOURCE, cache_key)
    if cached is not cache.MISS:
        return cached

    results = _search_albums(artist_name, limit=25, country=country)
    if not results:
        cache.put(SOURCE, cache_key, [])
        return []

    # Filter to entries whose artistName matches the queried artist.
    # We split on common feat/comma separators so collab albums still match
    # if our artist is one of the credited names.
    matches: list[dict] = []
    target = normalize(artist_name)
    for r in results:
        if r.get("wrapperType") != "collection":
            continue
        candidate = r.get("artistName", "")
        candidate_parts = re.split(
            r"\s*(?:,|&|\bfeat\.?\b|\band\b|\bx\b|\+|/)\s*",
            candidate, flags=re.IGNORECASE,
        )
        for part in candidate_parts:
            if normalize(part) == target:
                matches.append(r)
                break

    if not matches:
        # Fall back to looser containment match if exact-component failed
        for r in results:
            if r.get("wrapperType") != "collection":
                continue
            cn = normalize(r.get("artistName", ""))
            if target and (target == cn or (len(target) >= 4 and target in cn)):
                matches.append(r)

    # Sort newest first
    def _sort_key(r: dict) -> str:
        return r.get("releaseDate") or ""

    matches.sort(key=_sort_key, reverse=True)

    out: list[dict] = []
    seen_titles: set[str] = set()
    for album in matches:
        if len(out) >= top_n:
            break
        title = album.get("collectionName", "")
        # de-dupe by normalized title so we don't get 3 deluxe variants
        key = normalize(title)
        if key in seen_titles:
            continue
        seen_titles.add(key)

        copyright_text = (album.get("copyright") or "").strip()
        parsed = parse_pline(copyright_text)
        primary = parsed["owners"][0] if parsed["owners"] else ""

        out.append({
            "title": title,
            "label": primary,
            "copyright": copyright_text,
            "owners": parsed["owners"],
            "licensee": parsed["licensee"],
            "release_date": album.get("releaseDate", ""),
            "album_id": album.get("collectionId"),
        })

    polite_sleep(0.25)  # respectful pacing
    cache.put(SOURCE, cache_key, out)
    return out


def get_earliest_year(artist_name: str, country: str = "US") -> int | None:
    """Return the earliest release year found for this artist on Apple,
    or None if no releases found / not on Apple.

    Discogs and iTunes both have a long tail of namesake artists, so we
    only count releases whose artistName EXACTLY equals the queried
    artist (after normalization). This eliminates false old years from
    a different artist with the same first name.
    """
    ck = f"earliest|{artist_name}|{country}"
    cached = cache.get(SOURCE, ck)
    if cached is not cache.MISS:
        return cached

    results = _search_albums(artist_name, limit=200, country=country)
    target = normalize(artist_name)
    earliest: int | None = None
    for r in results:
        if r.get("wrapperType") != "collection":
            continue
        # STRICT exact-name match for the earliest-year heuristic.
        # Looser matching (containment, comma-split) is fine for fetching
        # current releases for the rule engine, but for the "is this
        # catalog older than 2005" decision we need confidence.
        cn = normalize(r.get("artistName", ""))
        if not cn or cn != target:
            continue
        rd = r.get("releaseDate") or ""
        m = re.match(r"^(\d{4})", rd)
        if m:
            year = int(m.group(1))
            if earliest is None or year < earliest:
                earliest = year

    cache.put(SOURCE, ck, earliest)
    return earliest


def labels_only(releases: Iterable[dict]) -> list[str]:
    """Every distinct owner+licensee string seen across the releases."""
    seen: list[str] = []
    for r in releases:
        for owner in r.get("owners", []):
            if owner and owner not in seen:
                seen.append(owner)
        lic = r.get("licensee")
        if lic and lic not in seen:
            seen.append(lic)
    return seen
