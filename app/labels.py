"""Label classification primitives.

Four pure functions everything else composes on top of:

  is_major_family(label)          -> bool
  is_distributor_only(label)      -> bool
  is_name_variant(artist, label)  -> bool
  find_licensing_clause(text)     -> Optional[str]

Plus normalize() for fuzzy comparison and split_owners() for parsing
multi-owner P-line strings without splitting on " and " / " & " inside an
artist's actual name (the bug that caused "Iron and Wine" to be flagged).
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Major-family tokens. Substring match, case-insensitive.
# ---------------------------------------------------------------------------
MAJOR_FAMILY_TOKENS = (
    # Universal
    "universal music", "universal records", "umg", "umg recordings",
    "polydor", "geffen", "capitol records", "capitol music",
    "vertigo records", "electrola", "back lot music",
    "universal studios music", "milan records",
    "mercury records", "mercury studios",
    "island records", "def jam", "interscope", "republic records",
    "republic music", "verve records", "decca records",
    # Sony
    "sony music", "sony classical", "columbia records", "rca records",
    "epic records", "arista records", "ariola", "hansa records",
    "provident music", "nitron music", "sevenone music",
    # Warner
    "warner music", "warner records", "warner bros records",
    "wmg", "wea", "atlantic records", "elektra records",
    "parlophone", "rhino records", "arts music",
    "watertower music", "x5 music group",
    # BMG / Disney / Hasbro / Mattel — major-equivalent for our purposes
    "bmg rights management", "bmg music",
    "walt disney records", "disney music", "hollywood records",
    "hasbro music", "mattel arts music",
    "arts music rhino",
    # Major distribution arms
    "netflix music",
)

# Known indies that we still want to flag (third-party indie deals are
# almost always exclusive; they're not what we're sourcing).
KNOWN_INDIES = (
    "sub pop", "merge records", "matador records", "4ad", "secretly canadian",
    "domino recording", "rough trade", "dead oceans", "jagjaguwar",
    "ninja tune", "warp records", "stones throw",
    "fat possum", "saddle creek", "epitaph", "anti-",
    "monstercat", "armada music", "spinnin records",
)

# Distributor placeholders that pass as clean — these mean "self-released
# through a distributor," which is what we WANT.
DISTRIBUTOR_TOKENS = (
    "distrokid", "tunecore", "cd baby", "cdbaby",
    "amuse", "landr", "unitedmasters", "united masters",
    "ditto music", "ditto", "stem", "routenote", "imusician",
    "horus music", "label engine", "mediacube", "musichub",
    "recordjet", "igroovemusic", "tratore", "altafonte",
    "believe music", "believe digital",
    # Generic Spotify/Apple-style numeric placeholders for DistroKid uploads
    # are matched separately by the regex below.
)

# DistroKid auto-generates labels like "1234567 Records DK" or
# "9876543 Records DK2". These are clean.
_DISTROKID_NUMERIC_RE = re.compile(r"^\d{4,}\s+records\s+dk\d*$", re.I)

# Corporate suffixes we strip when comparing label core to artist name.
_SUFFIX_TOKENS = {
    "records", "recordings", "recording",
    "music", "musik", "musique",
    "productions", "production", "produkties",
    "entertainment", "ent", "ent.",
    "ltd", "ltd.", "llc", "inc", "inc.", "gmbh", "co", "co.",
    "media", "studios", "studio",
    "international", "intl", "intl.",
    "kids", "band", "group",
    "oficial", "official",
    "rec", "rec.", "recordz",
    "music group", "label",
    "publishing", "songs",
    "sa", "s.a.", "spa", "pty", "ag", "bv", "b.v.",
    "ministries",
}

# Two-word suffixes (must be checked before single-word suffixes).
_TWO_WORD_SUFFIXES = {
    ("music", "group"),
    ("s", "a"),  # S.A. (already split by punctuation strip)
    ("co", "ltd"),
    ("pty", "ltd"),
}

# Soft licensing markers (only flag when followed by major/indie)
_SOFT_LICENSE_MARKERS = (
    "a division of",
    "a label of",
    "distributed by",
    "distribuido por",
)

# Hard licensing markers (always flag)
_HARD_LICENSE_MARKERS = (
    "under exclusive license to",
    "under exclusive licence to",
    "under license to",
    "under licence to",
    "exclusively licensed to",
    "exclusively licensed for",
    "licensee for",
    "licenciado a",
    "bajo licencia exclusiva",
    "licencia exclusiva",
    "sob licença exclusiva",
    "sous licence exclusive",
    "exclusive licence to",
    "exclusive license to",
)


def normalize(s: str) -> str:
    """Lowercase, strip diacritics, drop punctuation, collapse whitespace."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_suffixes(tokens: List[str]) -> List[str]:
    """Drops trailing corporate-suffix words. Repeats until stable."""
    out = list(tokens)
    changed = True
    while changed and out:
        changed = False
        # try two-word suffix first
        if len(out) >= 2 and (out[-2], out[-1]) in _TWO_WORD_SUFFIXES:
            out = out[:-2]
            changed = True
            continue
        if out and out[-1] in _SUFFIX_TOKENS:
            out = out[:-1]
            changed = True
    return out


def _singularize(tok: str) -> str:
    """Naive plural fold: nursery rhymes ↔ nursery rhyme. Only strips
    a trailing 's' if the rest is at least 3 chars (so 'us' / 'is' /
    short stems aren't mangled)."""
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _word_contains(haystack_tokens: List[str], needle: str) -> bool:
    """True if `needle` (which may be 1+ space-separated words) appears as a
    contiguous run of WHOLE tokens in haystack_tokens. This avoids false
    matches like 'ume' matching inside 'mathumela'.
    """
    needle_tokens = needle.split()
    if not needle_tokens:
        return False
    n = len(needle_tokens)
    for i in range(len(haystack_tokens) - n + 1):
        if haystack_tokens[i : i + n] == needle_tokens:
            return True
    return False


def is_major_family(label: str) -> bool:
    if not label:
        return False
    haystack = normalize(label).split()
    for tok in MAJOR_FAMILY_TOKENS:
        if _word_contains(haystack, normalize(tok)):
            return True
    return False


def is_known_indie(label: str) -> bool:
    if not label:
        return False
    haystack = normalize(label).split()
    return any(_word_contains(haystack, normalize(i)) for i in KNOWN_INDIES)


def is_distributor_only(label: str) -> bool:
    if not label:
        return False
    if _DISTROKID_NUMERIC_RE.match(label.strip()):
        return True
    haystack = normalize(label).split()
    return any(_word_contains(haystack, normalize(t)) for t in DISTRIBUTOR_TOKENS)


def is_name_variant(artist: str, label: str) -> bool:
    """True if label, after normalization and corporate-suffix stripping,
    is the artist's name OR a token-prefix relationship in either direction.

    Examples that match:
      'Drake' ↔ 'Drake Productions'
      'Nursery Rhymes' ↔ 'Nursery Rhyme Productions'  (singular fold)
      'Yancy' ↔ 'Yancy Ministries, Inc.'
      'Gracie\\'s Corner' ↔ 'Gracie\\'s Corner LLC'
    """
    if not artist or not label:
        return False
    a_tokens = normalize(artist).split()
    l_tokens = normalize(label).split()
    if not a_tokens or not l_tokens:
        return False
    a_core = _strip_suffixes(a_tokens)
    l_core = _strip_suffixes(l_tokens)
    if not a_core or not l_core:
        return False

    # Apply singular-fold to last token of the SHORTER side, so
    # "Nursery Rhymes" (len 2) matches "Nursery Rhyme Productions" -> "Nursery Rhyme"
    if len(a_core) <= len(l_core):
        a_core = a_core[:-1] + [_singularize(a_core[-1])]
        l_core = l_core[:-1] + [_singularize(l_core[-1])] if l_core else l_core
    else:
        l_core = l_core[:-1] + [_singularize(l_core[-1])] if l_core else l_core
        a_core = a_core[:-1] + [_singularize(a_core[-1])]

    if a_core == l_core:
        return True
    # token-prefix in either direction
    if len(a_core) <= len(l_core) and l_core[: len(a_core)] == a_core:
        return True
    if len(l_core) <= len(a_core) and a_core[: len(l_core)] == l_core:
        return True
    return False


def find_licensing_clause(text: str) -> Optional[str]:
    """Returns a short description of a licensing/distribution clause if
    found, else None. Soft markers ('distributed by X') only fire when X
    is a major or known indie."""
    if not text:
        return None
    n = normalize(text)
    for marker in _HARD_LICENSE_MARKERS:
        m = normalize(marker)
        if m in n:
            # Take the rest of the original text after the marker for the licensee
            idx = n.find(m)
            tail = n[idx + len(m):].strip()
            licensee = tail.split(",")[0].split(".")[0][:80].strip()
            return licensee or marker
    for marker in _SOFT_LICENSE_MARKERS:
        m = normalize(marker)
        idx = n.find(m)
        if idx < 0:
            continue
        tail = n[idx + len(m):].strip()
        licensee = tail.split(",")[0].split(".")[0][:80].strip()
        if licensee and (is_major_family(licensee) or is_known_indie(licensee)):
            return licensee
    return None


# Backward-compat alias used by sources/itunes.py
def find_licensee(text: str) -> Optional[str]:
    return find_licensing_clause(text)


# ---------------------------------------------------------------------------
# split_owners — the iTunes parser fix.
#
# Apple writes joint imprints with " / " or "; " or "and" only WHEN both
# sides are full-fledged label entities. Inside an artist name " and " /
# " & " is just connective tissue (Iron and Wine, Tegan and Sara, Earth,
# Wind & Fire).
#
# Rule: only split on a separator if the LEFT side ends with a corporate-
# suffix terminator. Otherwise treat the whole thing as one owner.
# ---------------------------------------------------------------------------
_ENTITY_TERMINATORS = (
    "records", "recordings", "music", "musik", "musique",
    "productions", "production", "entertainment", "ent",
    "ltd", "llc", "inc", "gmbh", "co", "media", "studios",
    "international", "publishing", "ministries", "rec", "recordz",
    "musique", "label", "group",
)

_BRACKET_RE = re.compile(r"[\[(]([^\])]*)[\])]")


def _ends_with_terminator(text: str) -> bool:
    toks = normalize(text).split()
    return bool(toks) and toks[-1] in _ENTITY_TERMINATORS


def split_owners(p_line_or_owner_text: str) -> List[str]:
    """Splits a multi-owner P-line text into individual owner strings.
    Conservative: refuses to split on ' and ' / ' & ' unless the left side
    ends with a corporate-suffix word. This fixes the Iron and Wine / Tegan
    and Sara false-flag bug.
    """
    if not p_line_or_owner_text:
        return []
    raw = p_line_or_owner_text.strip()

    # Strip bracket annotations like "[dist. Tratore]" — those are metadata,
    # not joint owners. Capture them separately so the audit can use them
    # as distributor hints if needed.
    annotations: List[str] = []

    def _capture(m: re.Match) -> str:
        annotations.append(m.group(1))
        return ""

    raw = _BRACKET_RE.sub(_capture, raw).strip(" ,;-")
    # Also handle "dist. Foo" without brackets
    raw = re.sub(r"\bdist\.\s+([A-Za-z0-9 &.'\-]+?)(?=,|;|$)", "", raw, flags=re.I)
    raw = raw.strip(" ,;-")

    parts: List[str] = []
    # Hard separators: " / ", "; "
    candidates = re.split(r"\s*/\s*|\s*;\s*", raw)
    for cand in candidates:
        cand = cand.strip()
        if not cand:
            continue
        # Try to split on " and " / " & " ONLY if left side terminates an entity
        # We do this iteratively to handle "X Records and Y Records and Z Records"
        sub = [cand]
        again = True
        while again:
            again = False
            new_sub = []
            for piece in sub:
                # search for first " and "/" & " whose left side ends in a terminator
                m = re.search(r"\s+(?:and|&)\s+", piece, re.I)
                while m:
                    left = piece[: m.start()].rstrip()
                    if _ends_with_terminator(left):
                        new_sub.append(left)
                        piece = piece[m.end():].lstrip()
                        again = True
                        m = re.search(r"\s+(?:and|&)\s+", piece, re.I)
                    else:
                        # not a real split, leave it
                        m = None
                new_sub.append(piece)
            sub = [s for s in new_sub if s]
        parts.extend(sub)

    # Append annotations as extra entries so callers can see them
    parts.extend(annotations)
    return [p.strip(" ,;-") for p in parts if p.strip(" ,;-")]


def classify_label(artist: str, label: str) -> str:
    """Returns one of: 'major', 'licensed', 'distributor', 'variant',
    'thirdparty'. Used by audit.py to roll up per-label evaluations."""
    if is_major_family(label):
        return "major"
    licensee = find_licensing_clause(label)
    if licensee:
        return "licensed"
    if is_distributor_only(label):
        return "distributor"
    if is_name_variant(artist, label):
        return "variant"
    return "thirdparty"
