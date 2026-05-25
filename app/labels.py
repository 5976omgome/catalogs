"""Label classification rules.

Single source of truth for what counts as a major, indie, distributor,
or self-release. Easy to edit without touching audit logic.
"""
from __future__ import annotations

import re
from typing import Literal

LabelType = Literal["major", "indie", "distributor", "self", "other", "none"]

# Catalog age threshold: artists whose earliest known release is BEFORE
# this year are considered too established for the catalog-acquisition
# play and get flagged automatically.
OLD_CATALOG_CUTOFF = 2005

# Major label imprints and parents.
MAJORS: tuple[str, ...] = (
    # Universal
    "universal music", "umg", "republic records", "def jam", "interscope",
    "capitol records", "island records", "motown", "geffen", "virgin records",
    "polydor", "mercury records", "verve", "decca", "emi",
    # Sony
    "sony music", "smg", "columbia records", "rca records", "epic records",
    "arista", "jive records", "legacy recordings", "rca inspiration",
    # Warner
    "warner records", "warner music", "wmg", "atlantic records", "atlantic",
    "elektra", "parlophone", "sire records", "wea", "rhino entertainment",
    "300 entertainment", "asylum records", "reprise records",
)

# Recognizable indie labels we want to filter out.
INDIES: tuple[str, ...] = (
    "merlin", "beggars", "4ad", "matador records", "sub pop",
    "secretly canadian", "jagjaguwar", "dead oceans", "warp records",
    "rough trade", "domino recording", "ninja tune", "monstercat",
    "ingrooves", "empire distribution", "alamo records", "because music",
    "play music", "believe music", "mom + pop music", "anti- records",
    "fat possum", "stones throw", "ghostly international", "fool's gold",
    "ed banger", "kitsuné", "kitsune", "soulection",
)

# Distributors are NOT a label deal — these get a free pass.
DISTRIBUTORS: tuple[str, ...] = (
    "distrokid", "tunecore", "cdbaby", "cd baby", "amuse", "landr",
    "unitedmasters", "united masters", "stem", "repost network",
    "ditto music", "ditto", "routenote", "symphonic distribution",
    "symphonic", "awal", "the orchard", "horus music", "fuga",
    "octiive", "songtrust",
)

# Common self-release suffix words. If the label is "<artist><suffix>"
# we treat it as self-released.
SELF_SUFFIXES: tuple[str, ...] = (
    "music", "records", "recordings", "recs", "ent", "entertainment",
    "productions", "prod", "studios", "studio", "media", "group",
    "ltd", "llc", "inc", "co", "company", "official", "label",
    "publishing", "tapes", "sounds", "sound",
)


def normalize(s: str | None) -> str:
    """Lowercase and strip everything except letters and digits."""
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(n in haystack for n in needles)


def classify_label(label: str | None) -> LabelType:
    """Bucket a raw label string."""
    if not label:
        return "none"
    ll = label.lower().strip()
    if _contains_any(ll, DISTRIBUTORS):
        return "distributor"
    if _contains_any(ll, MAJORS):
        return "major"
    if _contains_any(ll, INDIES):
        return "indie"
    return "other"


def is_distributor(label: str | None) -> bool:
    """True if the label is a known DIY distributor (DistroKid/CDBaby/etc.)."""
    if not label:
        return False
    return _contains_any(label.lower().strip(), DISTRIBUTORS)


def is_exact_artist_match(artist_name: str, label: str | None) -> bool:
    """True only if the label normalized equals the artist name normalized.

    This is the STRICTEST possible self-release check: the label string
    is literally the artist's name, no suffix, no additions.
    """
    if not artist_name or not label:
        return False
    return normalize(artist_name) == normalize(label)


def is_self_released(artist_name: str, label: str | None,
                     strict: bool = False) -> bool:
    """Self-release check.

    strict=False (default, lenient mode used for cross-checks):
      1. Empty / "none" / "[no label]" -> self-released.
      2. Distributor name in the label -> self-released.
      3. Normalized label equals normalized artist name -> self-released.
      4. Normalized label equals artist name + a recognized suffix word
         (e.g. "Drake Music", "Drake Records") -> self-released.
      5. Anything else -> NOT self-released.

    strict=True (used for the final CLEAN verdict):
      1. Empty -> NOT self-released. We require positive evidence.
      2. Distributor name -> self-released.
      3. EXACT artist-name match -> self-released.
      4. Anything else (including "Artist Music", "Artist Records",
         self-imprints with creative names, etc.) -> NOT self-released.

    This is intentionally aggressive. It avoids the "Drake Music Group"
    pitfall and per the user's spec, even self-named imprints like
    "Russ My Way Inc." should NOT auto-pass as CLEAN -- they get
    flagged for manual review instead.
    """
    if not label:
        # Lenient mode treats "no label" as self-release; strict treats it
        # as inconclusive (we want positive proof).
        return not strict
    ll = label.lower().strip()
    if ll in ("none", "[no label]", "not on label"):
        return not strict
    if _contains_any(ll, DISTRIBUTORS):
        return True

    artist_norm = normalize(artist_name)
    label_norm = normalize(label)
    if not artist_norm:
        return False

    if artist_norm == label_norm:
        return True

    if strict:
        return False

    # Lenient suffix check
    if label_norm.startswith(artist_norm):
        remainder = label_norm[len(artist_norm):]
        if remainder in {normalize(s) for s in SELF_SUFFIXES}:
            return True
        if remainder.isdigit():
            return True

    if label_norm.endswith(artist_norm):
        remainder = label_norm[: -len(artist_norm)]
        if remainder in {normalize(s) for s in SELF_SUFFIXES}:
            return True

    return False


def is_likely_self_imprint(artist_name: str, label: str | None) -> bool:
    """True if the label LOOKS like a self-imprint (artist name + suffix
    pattern) but is not an exact match.

    We use this to flag rows for manual review without auto-clearing them.
    Distributors are NOT self-imprints; they are a separate clean category.
    """
    if not label or not artist_name:
        return False
    if is_distributor(label):
        return False
    if is_exact_artist_match(artist_name, label):
        return False  # exact match is its own thing
    return is_self_released(artist_name, label, strict=False)
