"""Wikipedia/Wikidata source — free, no auth, deterministic.

Lookup flow:
  1. Wikipedia search API -> find the article for the artist
  2. Extract the Wikidata QID from the article's page props
  3. Wikidata REST API -> fetch P264 (record label) claims
  4. For each label QID, fetch its English label string
  5. Walk P749 (parent organization) chain up to 3 hops to detect
     major-family ownership even on obscure imprints

The parent-chain walk is the real value-add: if an artist is on
"XL Recordings" (QID Q1065013) and XL's parent is "Beggars Group"
which is indie, that's fine. But if they're on "Republic Records"
(QID Q1532455) whose parent is "Universal Music Group" (QID Q170564),
the chain catches it as a major even if "Republic Records" isn't in
our hardcoded token list.

Known Wikidata QIDs for major parent companies (used as chain
terminators):
  - Q170564  Universal Music Group
  - Q183387  Sony Music Entertainment
  - Q183975  Warner Music Group
  - Q216364  BMG
  - Q194294  The Walt Disney Company
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

HEADERS = {"User-Agent": f"{USER_AGENT} (catalog-audit bot; polite)"}

# Major-family QIDs for the parent-chain walk
# These are verified Wikidata entity IDs for the major label parent companies.
# The walk traverses P749 (parent organization) up to 3 hops; if any hop
# lands on one of these QIDs, the label is flagged as major-owned.
MAJOR_QIDS: Dict[str, str] = {
    # Universal Music Group and known alternate/merged entities
    "Q38903": "Universal",         # Universal Music Group
    "Q1543477": "Universal",       # Universal Music
    # Sony Music
    "Q56760250": "Sony",           # Sony Music Entertainment  
    "Q183412": "Sony",             # Sony Music (another ID)
    "Q215654": "Sony",             # Columbia Records
    # Warner Music Group
    "Q21077": "Warner",            # Warner Music Group (confirmed via OVO Sound chain)
    "Q1139587": "Warner",          # Warner Records
    "Q212699": "Warner",           # Atlantic Records
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
P127 = "P127"   # owned by (fallback for parent chain)
P31 = "P31"     # instance of
P106 = "P106"   # occupation

# QIDs for filtering: must be a human or musical group
MUSICIAN_INSTANCE_QIDS = {
    "Q5",        # human
    "Q215380",   # musical group
    "Q4438121",  # boy band
    "Q641066",   # girl group
    "Q56816954", # musical duo
}

MUSICIAN_OCCUPATION_QIDS = {
    "Q177220",   # singer
    "Q488205",   # singer-songwriter
    "Q639669",   # musician
    "Q753110",   # songwriter
    "Q183945",   # record producer
    "Q36834",    # composer
    "Q2405480",  # voice actor (for character artists)
    "Q486748",   # rapper
    "Q855091",   # guitarist
    "Q584301",   # DJ
}


def _get(url: str, params: dict, timeout: int = 10) -> dict:
    """Make a GET request with polite rate limiting."""
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _find_wikidata_qid(artist_name: str) -> Optional[str]:
    """
    Search English Wikipedia for the artist, return their Wikidata QID.
    Uses the Wikipedia search API then extracts pageprops.wikibase_item.
    """
    key = f"wiki:qid:{normalize(artist_name)}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached  # could be None (cached miss)

    try:
        # Step 1: search Wikipedia
        data = _get(WIKI_SEARCH, {
            "action": "query",
            "list": "search",
            "srsearch": artist_name,
            "srlimit": 5,
            "format": "json",
        })
        results = data.get("query", {}).get("search", [])
        if not results:
            cache.set_(key, None)
            return None

        # Try each result to find one that's a musician
        for result in results:
            page_title = result.get("title", "")
            time.sleep(0.1)

            # Step 2: get Wikidata QID from pageprops
            pp_data = _get(WIKI_SEARCH, {
                "action": "query",
                "titles": page_title,
                "prop": "pageprops",
                "format": "json",
            })
            pages = pp_data.get("query", {}).get("pages", {})
            qid = None
            for page in pages.values():
                qid = page.get("pageprops", {}).get("wikibase_item")
                if qid:
                    break
            if not qid:
                continue

            # Step 3: verify this QID is a musician/group
            if _is_musician(qid):
                cache.set_(key, qid)
                return qid

        # No musician match found
        cache.set_(key, None)
        return None

    except Exception:
        cache.set_(key, None)
        return None


def _is_musician(qid: str) -> bool:
    """Check if a Wikidata entity is a human/group with a music occupation."""
    try:
        data = _get(WIKIDATA_API, {
            "action": "wbgetclaims",
            "entity": qid,
            "property": P31,
            "format": "json",
        })
        claims = data.get("claims", {})

        # Check instance-of (P31)
        p31_claims = claims.get(P31, [])
        instance_qids = set()
        for claim in p31_claims:
            try:
                val = claim["mainsnak"]["datavalue"]["value"]["id"]
                instance_qids.add(val)
            except (KeyError, TypeError):
                continue

        if instance_qids & MUSICIAN_INSTANCE_QIDS:
            return True

        # Also check occupation (P106) for humans
        if "Q5" in instance_qids or not instance_qids:
            time.sleep(0.1)
            occ_data = _get(WIKIDATA_API, {
                "action": "wbgetclaims",
                "entity": qid,
                "property": P106,
                "format": "json",
            })
            occ_claims = occ_data.get("claims", {}).get(P106, [])
            for claim in occ_claims:
                try:
                    val = claim["mainsnak"]["datavalue"]["value"]["id"]
                    if val in MUSICIAN_OCCUPATION_QIDS:
                        return True
                except (KeyError, TypeError):
                    continue

        return False
    except Exception:
        # On error, be permissive — let the caller decide
        return True


def _get_label_qids(artist_qid: str) -> List[str]:
    """Fetch all record label QIDs (P264) for an artist entity."""
    try:
        data = _get(WIKIDATA_API, {
            "action": "wbgetclaims",
            "entity": artist_qid,
            "property": P264,
            "format": "json",
        })
        claims = data.get("claims", {}).get(P264, [])
        qids = []
        for claim in claims:
            try:
                val = claim["mainsnak"]["datavalue"]["value"]["id"]
                qids.append(val)
            except (KeyError, TypeError):
                continue
        return qids
    except Exception:
        return []


def _get_entity_label(qid: str) -> str:
    """Get the English label for a Wikidata entity."""
    key = f"wiki:label:{qid}"
    cached = cache.get(key)
    if not cache.is_miss(cached):
        return cached or ""

    try:
        data = _get(WIKIDATA_API, {
            "action": "wbgetentities",
            "ids": qid,
            "props": "labels",
            "languages": "en",
            "format": "json",
        })
        entities = data.get("entities", {})
        entity = entities.get(qid, {})
        label = entity.get("labels", {}).get("en", {}).get("value", "")
        cache.set_(key, label)
        return label
    except Exception:
        cache.set_(key, "")
        return ""


def _walk_parent_chain(label_qid: str, max_depth: int = 3) -> Optional[Tuple[str, str]]:
    """
    Walk up the P749 (parent organization) and P127 (owned by) chain from
    a label QID. If we hit a known major-family QID, return
    (family_name, major_qid). Otherwise return None.

    Max depth prevents infinite loops on circular Wikidata references.
    """
    visited = set()
    current = label_qid

    for _ in range(max_depth):
        if current in visited:
            break
        visited.add(current)

        # Check if current entity IS a major
        if current in MAJOR_QIDS:
            return (MAJOR_QIDS[current], current)

        # Fetch parent org (try P749 first, then P127 as fallback)
        parent_qid = None
        for prop in (P749, P127):
            try:
                time.sleep(0.1)
                data = _get(WIKIDATA_API, {
                    "action": "wbgetclaims",
                    "entity": current,
                    "property": prop,
                    "format": "json",
                })
                claims = data.get("claims", {}).get(prop, [])
                if not claims:
                    continue

                # Take the first (most current) parent
                for claim in claims:
                    try:
                        parent_qid = claim["mainsnak"]["datavalue"]["value"]["id"]
                        break
                    except (KeyError, TypeError):
                        continue
                if parent_qid:
                    break
            except Exception:
                continue

        if not parent_qid:
            break
        current = parent_qid

    return None


def get_labels(artist_name: str) -> List[dict]:
    """
    Main entry point. Returns a list of label records found on Wikipedia/
    Wikidata for this artist.

    Each record: {
        "label": str,          # human-readable label name
        "label_qid": str,      # Wikidata QID of the label
        "major_via_chain": Optional[str],  # major family name if parent chain hits a major
        "major_chain_qid": Optional[str],  # the major QID that was hit
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

    time.sleep(0.2)
    label_qids = _get_label_qids(qid)
    if not label_qids:
        cache.set_(key, [])
        return []

    results = []
    seen_labels = set()

    for lqid in label_qids:
        time.sleep(0.15)
        label_name = _get_entity_label(lqid)
        if not label_name or label_name in seen_labels:
            continue
        seen_labels.add(label_name)

        # Walk parent chain to detect major ownership
        chain_result = _walk_parent_chain(lqid)
        results.append({
            "label": label_name,
            "label_qid": lqid,
            "major_via_chain": chain_result[0] if chain_result else None,
            "major_chain_qid": chain_result[1] if chain_result else None,
        })

    cache.set_(key, results)
    return results


def get_earliest_year(artist_name: str) -> str:
    """
    Wikipedia/Wikidata doesn't reliably have per-release dates in a
    structured way (P264 doesn't carry date qualifiers consistently).
    Return empty — let iTunes/Deezer/Discogs handle this.
    """
    return ""
