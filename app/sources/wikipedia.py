"""Wikipedia/Wikidata source — free, no auth, deterministic.

Redesigned for reliability:
  - Aggressive caching at every level (QID, labels, parent chain)
  - Rate-limit aware: backs off on 429, retries once after delay
  - Disambiguation: searches with "(musician)" / "(band)" suffix first
  - Minimal API calls: batch entity fetches where possible
  - Parent chain results are cached per-label-QID so the same label
    (e.g., Republic Records) is only walked once ever

The goal is to surface historical label affiliations from Wikipedia's
structured data. This catches deals/signings that iTunes P-lines might
not show (because the P-line only reflects the CURRENT release's owner,
not the artist's full history).
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import requests

from .. import cache
from ..config import USER_AGENT
from ..labels import normalize

# Wikipedia / Wikidata endpoints
WIKI_SEARCH = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

HEADERS = {"User-Agent": f"{USER_AGENT} (catalog-audit/1.0; contact: github.com/5976omgome)"}

# Verified major-family QIDs (confirmed via live API tests).
# The parent-chain walk checks each hop against this set.
MAJOR_QIDS: Dict[str, str] = {
    # Warner Music Group
    "Q21077": "Warner",            # Warner Music Group (confirmed)
    "Q1139587": "Warner",          # Warner Records
    "Q212699": "Warner",           # Atlantic Records
    "Q726251": "Warner",           # Elektra Records
    # Universal Music Group
    "Q38903": "Universal",         # Universal Music Group
    "Q4413456": "Universal",       # Republic Records (confirmed child of UMG)
    "Q202440": "Universal",        # Interscope Records
    "Q216364": "Universal",        # Def Jam Recordings
    "Q183746": "Universal",        # Island Records
    "Q1088498": "Universal",       # Geffen Records
    "Q1439985": "Universal",       # Polydor Records
    # Sony Music Entertainment
    "Q168407": "Sony",             # Sony Music Entertainment
    "Q183412": "Sony",             # Sony Music (alternate)
    "Q215654": "Sony",             # Columbia Records
    "Q386773": "Sony",             # Epic Records
    "Q1124849": "Sony",            # RCA Records
    "Q1142691": "Sony",            # Arista Records
    # BMG
    "Q217845": "BMG",              # Bertelsmann Music Group
    "Q684898": "BMG",              # BMG Rights Management
    # Disney
    "Q142": "Disney",              # The Walt Disney Company
    "Q1020941": "Disney",          # Walt Disney Records
}

# Wikidata properties
P264 = "P264"   # record label
P749 = "P749"   # parent organization
P127 = "P127"   # owned by
P31 = "P31"     # instance of
P106 = "P106"   # occupation

# Instance-of QIDs that identify a musician/group entity
_MUSICIAN_TYPES = {
    "Q5",         # human
    "Q215380",    # musical group
    "Q4438121",   # boy band
    "Q641066",    # girl group
    "Q56816954",  # musical duo
    "Q2088357",   # musical ensemble
}

# Occupation QIDs for humans
_MUSICIAN_OCCS = {
    "Q177220",    # singer
    "Q488205",    # singer-songwriter
    "Q639669",    # musician
    "Q753110",    # songwriter
    "Q183945",    # record producer
    "Q36834",     # composer
    "Q486748",    # rapper
    "Q855091",    # guitarist
    "Q584301",    # DJ
    "Q2405480",   # voice actor
    "Q15981151",  # lyricist
}

# How long to wait after a rate-limit before retrying
_RATE_LIMIT_WAIT = 2.0
# Polite delay between normal requests
_POLITE_DELAY = 0.15


def _get_safe(url: str, params: dict, timeout: int = 12) -> Optional[dict]:
    """
    Make a GET request with:
    - Polite User-Agent
    - Rate-limit awareness (429 → wait and retry once)
    - Graceful failure (returns None instead of raising)
    """
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code == 429:
            # Rate limited — wait and retry once
            time.sleep(_RATE_LIMIT_WAIT)
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 429:
                return None  # Still limited, give up gracefully
        if r.status_code != 200:
            return None
        data = r.json()
        # Wikidata sometimes returns errors inside a 200 response
        if "error" in data:
            return None
        return data
    except Exception:
        return None


def _find_wikidata_qid(artist_name: str) -> Optional[str]:
    """
    Search Wikipedia for the artist and return their Wikidata QID.

    Strategy:
    1. Search with "(musician)" suffix for disambiguation
    2. If no results, search with "(band)" suffix
    3. If still nothing, search the bare name
    4. For each candidate, check if it's a musician via P31/P106
       (but only make 1 verification call per candidate, not 2)
    """
    key = f"wiki:qid:{normalize(artist_name)}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    # Try disambiguation-aware searches first, then bare name
    search_variants = [
        f"{artist_name} musician",
        f"{artist_name} band",
        artist_name,
    ]

    for query in search_variants:
        time.sleep(_POLITE_DELAY)
        data = _get_safe(WIKI_SEARCH, {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "format": "json",
        })
        if not data:
            continue

        results = data.get("query", {}).get("search", [])
        if not results:
            continue

        for result in results:
            page_title = result.get("title", "")
            time.sleep(_POLITE_DELAY)

            # Get Wikidata QID from page properties
            pp_data = _get_safe(WIKI_SEARCH, {
                "action": "query",
                "titles": page_title,
                "prop": "pageprops",
                "format": "json",
            })
            if not pp_data:
                continue

            pages = pp_data.get("query", {}).get("pages", {})
            qid = None
            for page in pages.values():
                qid = page.get("pageprops", {}).get("wikibase_item")
                if qid:
                    break
            if not qid:
                continue

            # Verify it's a musician/group in ONE call (fetch P31 + P106 together)
            if _is_musician_fast(qid):
                cache.set_(key, qid)
                return qid

    # Nothing found
    cache.set_(key, None)
    return None


def _is_musician_fast(qid: str) -> bool:
    """
    Check if a Wikidata entity is a musician/group using a single API call
    that fetches both P31 (instance-of) and P106 (occupation) at once.
    """
    cache_key = f"wiki:is_musician:{qid}"
    cached = cache.get(cache_key)
    if not cache.is_miss(cached):
        return cached

    time.sleep(_POLITE_DELAY)
    # Fetch the full entity's claims for P31 and P106 in one request
    data = _get_safe(WIKIDATA_API, {
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims",
        "format": "json",
    })
    if not data:
        # On failure, be permissive — assume it might be a musician
        return True

    entity = data.get("entities", {}).get(qid, {})
    claims = entity.get("claims", {})

    # Check P31 (instance of)
    p31_vals = set()
    for claim in claims.get(P31, []):
        try:
            p31_vals.add(claim["mainsnak"]["datavalue"]["value"]["id"])
        except (KeyError, TypeError):
            continue

    if p31_vals & _MUSICIAN_TYPES:
        cache.set_(cache_key, True)
        return True

    # For humans (Q5), also check P106 (occupation)
    if "Q5" in p31_vals or not p31_vals:
        for claim in claims.get(P106, []):
            try:
                occ = claim["mainsnak"]["datavalue"]["value"]["id"]
                if occ in _MUSICIAN_OCCS:
                    cache.set_(cache_key, True)
                    return True
            except (KeyError, TypeError):
                continue

    cache.set_(cache_key, False)
    return False


def _get_label_claims(artist_qid: str) -> List[dict]:
    """
    Fetch all P264 (record label) claims for an artist, returning the
    label QID plus any date qualifiers (P580 start time, P582 end time).

    Returns list of dicts: {qid, start_year, end_year}
    """
    time.sleep(_POLITE_DELAY)
    data = _get_safe(WIKIDATA_API, {
        "action": "wbgetclaims",
        "entity": artist_qid,
        "property": P264,
        "format": "json",
    })
    if not data:
        return []

    claims = data.get("claims", {}).get(P264, [])
    results = []

    for claim in claims:
        try:
            label_qid = claim["mainsnak"]["datavalue"]["value"]["id"]
        except (KeyError, TypeError):
            continue

        # Extract date qualifiers if present (P580=start, P582=end)
        qualifiers = claim.get("qualifiers", {})
        start_year = _extract_year_from_qualifier(qualifiers.get("P580", []))
        end_year = _extract_year_from_qualifier(qualifiers.get("P582", []))

        results.append({
            "qid": label_qid,
            "start_year": start_year,
            "end_year": end_year,
        })

    return results


def _extract_year_from_qualifier(qualifier_list: list) -> str:
    """Extract a year string from a Wikidata time qualifier."""
    for q in qualifier_list:
        try:
            time_val = q["datavalue"]["value"]["time"]
            # Format: "+2015-01-01T00:00:00Z" → "2015"
            if time_val and len(time_val) >= 5:
                year = time_val[1:5]  # skip the leading "+"
                if year.isdigit():
                    return year
        except (KeyError, TypeError, IndexError):
            continue
    return ""


def _get_entity_label(qid: str) -> str:
    """Get the English label for a Wikidata entity (cached)."""
    key = f"wiki:label:{qid}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached or ""

    time.sleep(_POLITE_DELAY)
    data = _get_safe(WIKIDATA_API, {
        "action": "wbgetentities",
        "ids": qid,
        "props": "labels",
        "languages": "en",
        "format": "json",
    })
    if not data:
        cache.set_(key, "")
        return ""

    entity = data.get("entities", {}).get(qid, {})
    label = entity.get("labels", {}).get("en", {}).get("value", "")
    cache.set_(key, label)
    return label


def _walk_parent_chain(label_qid: str, max_depth: int = 3) -> Optional[Tuple[str, str]]:
    """
    Walk up the P749/P127 chain from a label QID looking for a major parent.
    Returns (family_name, major_qid) or None.

    Results are cached per label_qid so the same label (e.g., Republic Records)
    is only walked once across all artists in a run.
    """
    cache_key = f"wiki:chain:{label_qid}"
    cached = cache.get(cache_key)
    if not cache.is_miss(cached):
        return tuple(cached) if cached else None

    visited = set()
    current = label_qid

    for _ in range(max_depth):
        if current in visited:
            break
        visited.add(current)

        # Check if current entity IS a major
        if current in MAJOR_QIDS:
            result = (MAJOR_QIDS[current], current)
            cache.set_(cache_key, list(result))
            return result

        # Try P749 first, then P127
        parent_qid = None
        for prop in (P749, P127):
            time.sleep(_POLITE_DELAY)
            data = _get_safe(WIKIDATA_API, {
                "action": "wbgetclaims",
                "entity": current,
                "property": prop,
                "format": "json",
            })
            if not data:
                continue

            claims = data.get("claims", {}).get(prop, [])
            for claim in claims:
                try:
                    parent_qid = claim["mainsnak"]["datavalue"]["value"]["id"]
                    break
                except (KeyError, TypeError):
                    continue
            if parent_qid:
                break

        if not parent_qid:
            break
        current = parent_qid

    # No major found in chain
    cache.set_(cache_key, None)
    return None


def get_labels(artist_name: str) -> List[dict]:
    """
    Main entry point. Returns label records found on Wikidata for this artist.

    Each record: {
        "label": str,              # human-readable label name
        "label_qid": str,          # Wikidata QID of the label
        "start_year": str,         # year the deal started (if known)
        "end_year": str,           # year the deal ended (if known)
        "major_via_chain": str|None,  # major family if parent chain hit
        "major_chain_qid": str|None,  # the QID that matched
    }

    Returns [] if the artist isn't found or has no P264 claims.
    """
    key = f"wiki:labels:{normalize(artist_name)}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached

    qid = _find_wikidata_qid(artist_name)
    if not qid:
        cache.set_(key, [])
        return []

    label_claims = _get_label_claims(qid)
    if not label_claims:
        cache.set_(key, [])
        return []

    results = []
    seen_labels = set()

    for claim in label_claims:
        lqid = claim["qid"]
        label_name = _get_entity_label(lqid)
        if not label_name or label_name in seen_labels:
            continue
        seen_labels.add(label_name)

        # Walk parent chain (cached per label QID)
        chain_result = _walk_parent_chain(lqid)

        results.append({
            "label": label_name,
            "label_qid": lqid,
            "start_year": claim.get("start_year", ""),
            "end_year": claim.get("end_year", ""),
            "major_via_chain": chain_result[0] if chain_result else None,
            "major_chain_qid": chain_result[1] if chain_result else None,
        })

    cache.set_(key, results)
    return results


def get_earliest_year(artist_name: str) -> str:
    """
    If Wikidata has date qualifiers on the P264 claims, return the earliest
    start_year found. Otherwise return empty.
    """
    labels = get_labels(artist_name)
    years = [r["start_year"] for r in labels if r.get("start_year")]
    return min(years) if years else ""
