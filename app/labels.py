"""Label classification engine.

Core primitives:
- is_major_family(label) — matches Universal/Sony/Warner/BMG/Disney family
- find_licensing_clause(text) — detects exclusive/licensed-to language
- is_name_variant(artist, label) — does the label look like the artist's own imprint?
- is_distributor_only(label) — known neutral distributors (DistroKid, TuneCore, etc.)
- classify_label(artist, label) — returns one of: variant, distributor, major, licensed, thirdparty
- split_owners(pline_text) — splits a P-line into individual owner strings
"""
import re
import unicodedata
from typing import Optional

# ---------------------------------------------------------------------------
# Major-family token lists (word-boundary matched to avoid false positives
# like "mathumela" matching "ume")
# ---------------------------------------------------------------------------
_MAJOR_TOKENS = [
    # Universal family
    "universal", "umg", "ume", "polydor", "geffen", "capitol", "vertigo",
    "electrola", "karussell", "back lot music", "universal studios music",
    "milan records", "mercury", "island", "def jam", "interscope",
    "republic", "verve", "decca",
    # Sony family
    "sony", "columbia", "rca", "epic", "arista", "ariola", "hansa",
    "provident", "nitron", "gold league", "sevenone",
    # Warner family
    "warner", "wmg", "wea", "atlantic", "elektra", "parlophone",
    "rhino", "arts music", "watertower", "x5 music group", "ada",
    # BMG / Disney / Hasbro / Mattel (major-equivalent owners)
    "bmg rights management", "walt disney records", "disney music group",
    "hollywood records", "hasbro", "mattel", "arts music/rhino",
]

# Known indie labels to flag (not majors but still third-party encumbrances)
_KNOWN_INDIES = [
    "merlin", "beggars", "4ad", "matador", "sub pop", "secretly canadian",
    "jagjaguwar", "dead oceans", "warp", "rough trade", "domino",
    "ninja tune", "monstercat", "empire", "alamo",
]

# Neutral distributors — these pass as clean
_DISTRIBUTORS = [
    "distrokid", "tunecore", "cdbaby", "cd baby", "amuse", "landr",
    "unitedmasters", "united masters", "stem", "repost network",
    "ditto", "ditto music", "routenote", "recordjet", "igroovemusic.com",
    "imusician", "believe music", "mediacube music", "musichub",
    "tratore", "altafonte",
]

# These only match as exact (normalized) equals — not prefix/suffix
_DISTRIBUTORS_EXACT_ONLY = ["independent"]

# Corporate suffixes to strip for name-variant comparison
_SUFFIXES = [
    "records", "recordings", "recordz", "rec", "music", "productions",
    "production", "entertainment", "ent", "ltd", "llc", "inc", "gmbh",
    "s.a.", "s.a. de c.v.", "pty ltd", "oficial", "official", "group",
    "co", "studios", "media", "international", "kids", "band",
    "ministries", "digital", "label", "distribution",
]

# Licensing markers (multi-language)
_LICENSING_MARKERS = [
    "under exclusive license to",
    "under exclusive licence to",
    "exclusively licensed to",
    "exclusively distributed by",
    "licensed to",
    "licensee for",
    "licencia exclusiva",
    "sous licence exclusive",
    "bajo licencia exclusiva",
    "unter exklusiver lizenz",
]

# Soft licensing markers that only flag when followed by a major/indie name
_SOFT_LICENSING_MARKERS = [
    "exclusively licensed by",
    "distributed by",
    "a division of",
    "a label of",
]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase, strip diacritics, remove non-alphanumeric, collapse spaces."""
    if not s:
        return ""
    # Strip diacritics
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase and keep only alnum + space
    cleaned = re.sub(r"[^a-z0-9 ]", " ", ascii_str.lower())
    return " ".join(cleaned.split())


def _tokenize(s: str) -> list:
    """Split normalized string into tokens."""
    return _normalize(s).split()


def _strip_suffixes(tokens: list) -> list:
    """Remove trailing corporate suffix words from a token list."""
    suffix_set = {_normalize(s) for s in _SUFFIXES}
    # Also handle multi-word suffixes
    result = list(tokens)
    changed = True
    while changed and result:
        changed = False
        last = result[-1]
        if last in suffix_set:
            result.pop()
            changed = True
    return result


def _singularize_last(tokens: list) -> list:
    """Strip trailing 's' from last token for plural tolerance."""
    if not tokens:
        return tokens
    result = list(tokens)
    if result[-1].endswith("s") and len(result[-1]) > 3:
        result[-1] = result[-1][:-1]
    return result


# ---------------------------------------------------------------------------
# Word-boundary matching (prevents "mathumela" matching "ume")
# ---------------------------------------------------------------------------

def _word_boundary_match(text: str, token: str) -> bool:
    """Check if token appears in text as a complete word (word-boundary)."""
    pattern = r"\b" + re.escape(token) + r"\b"
    return bool(re.search(pattern, text))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Tokens that are common English words and only count as major when they
# appear at the START of the label name (prevents "Long Island Sound" matching "island")
_START_ANCHORED_TOKENS = {
    "island", "mercury", "republic", "atlantic", "capitol", "epic", "verve",
    "decca", "hansa",
}


def is_major_family(label: str) -> bool:
    """Does this label string contain a major-family token?

    All tokens use word-boundary matching. Tokens that are common English
    words (island, mercury, republic, etc.) additionally require appearing
    at the START of the label to prevent geographic/descriptive false positives.
    """
    ll = _normalize(label)
    for token in _MAJOR_TOKENS:
        if token in _START_ANCHORED_TOKENS:
            # Must appear at start of string (possibly after whitespace)
            if ll.startswith(token) or ll.startswith(token + " "):
                return True
            # Also match if preceded only by "the " (e.g., "The Atlantic")
            if ll.startswith("the " + token):
                return True
        else:
            if _word_boundary_match(ll, token):
                return True
    return False


# Tokens in the indie list that are common English words — require start-anchoring
# AND what follows must be empty or a corporate suffix
_INDIE_START_ANCHORED = {"empire", "alamo"}


def is_known_indie(label: str) -> bool:
    """Is this a known indie label we should flag?

    Uses word-boundary matching with start-anchoring for common English words.
    Start-anchored tokens require the remainder (after the token) to be empty
    or consist only of corporate suffixes like 'records', 'music', 'distribution'.
    This prevents 'Empire State Records' from matching the 'empire' token.
    """
    ll = _normalize(label)
    suffix_set = {_normalize(s) for s in _SUFFIXES}

    for token in _KNOWN_INDIES:
        if token in _INDIE_START_ANCHORED:
            if ll == token:
                return True
            if ll.startswith(token + " "):
                remainder_tokens = ll[len(token):].split()
                # All remaining words must be corporate suffixes
                if remainder_tokens and all(t in suffix_set for t in remainder_tokens):
                    return True
        else:
            if _word_boundary_match(ll, token):
                return True
    return False


def find_licensing_clause(text: str) -> Optional[str]:
    """If text contains exclusive/licensing language, return the licensee name.
    Returns None if no licensing clause found.
    """
    tl = text.lower()

    # Hard markers — always flag
    for marker in _LICENSING_MARKERS:
        idx = tl.find(marker)
        if idx >= 0:
            after = text[idx + len(marker):].strip(" ,;:")
            # Extract the licensee (up to next sentence boundary)
            licensee = re.split(r"[.!]|\ball\b", after, maxsplit=1)[0].strip()
            return licensee if licensee else marker

    # Soft markers — only flag if followed by a major or known indie
    for marker in _SOFT_LICENSING_MARKERS:
        idx = tl.find(marker)
        if idx >= 0:
            after = text[idx + len(marker):].strip(" ,;:")
            after_chunk = re.split(r"[.!,;]", after, maxsplit=1)[0].strip()
            if is_major_family(after_chunk) or is_known_indie(after_chunk):
                return after_chunk

    return None


def is_distributor_only(label: str) -> bool:
    """Is this label just a known neutral distributor?

    Stricter than major/indie matching: requires the label to essentially
    BE the distributor name (exact match, or distributor at the start/end
    of a short label string). Prevents false positives like
    'I Believe Music Is Life' matching 'believe music'.
    """
    ll = _normalize(label)
    if not ll:
        return False

    # Exact-only matches (e.g., "independent" — only matches the literal word)
    for d in _DISTRIBUTORS_EXACT_ONLY:
        if ll == _normalize(d):
            return True

    for d in _DISTRIBUTORS:
        nd = _normalize(d)
        # Exact match
        if nd == ll:
            return True
        # Label starts with the distributor name (e.g., "Believe Music UK")
        if ll.startswith(nd + " "):
            # Only if the extra part is short (country/region suffix)
            remainder = ll[len(nd) + 1:].strip()
            if len(remainder) <= 8:
                return True
        # Label ends with the distributor name (e.g., "via DistroKid")
        if ll.endswith(" " + nd):
            return True

    # Generic numeric "NNNNNNN Records DK" pattern (DistroKid placeholders)
    if re.match(r"^\d{5,} records dk\d?$", ll):
        return True
    return False


def is_name_variant(artist: str, label: str) -> bool:
    """Is the label a name variant of the artist?

    After normalizing both and stripping corporate suffixes:
    - Exact match, OR
    - Artist tokens are a prefix of label tokens, OR
    - Label tokens are a prefix of artist tokens.

    Includes singular/plural tolerance on the last token.
    """
    if not artist or not label:
        return False

    a_tokens = _strip_suffixes(_tokenize(artist))
    l_tokens = _strip_suffixes(_tokenize(label))

    if not a_tokens or not l_tokens:
        return False

    # Exact match
    if a_tokens == l_tokens:
        return True

    # Plural tolerance: try with singularized last tokens
    a_sing = _singularize_last(a_tokens)
    l_sing = _singularize_last(l_tokens)

    if a_sing == l_sing:
        return True

    # Prefix matching (artist is prefix of label or vice versa)
    def _is_prefix(shorter, longer):
        if len(shorter) > len(longer):
            return False
        for i, tok in enumerate(shorter):
            if tok != longer[i]:
                # Try singular tolerance on last token of shorter
                if i == len(shorter) - 1:
                    s1 = tok[:-1] if tok.endswith("s") and len(tok) > 3 else tok
                    s2 = longer[i][:-1] if longer[i].endswith("s") and len(longer[i]) > 3 else longer[i]
                    if s1 == s2:
                        return True
                return False
        return True

    if _is_prefix(a_tokens, l_tokens) or _is_prefix(l_tokens, a_tokens):
        return True
    if _is_prefix(a_sing, l_sing) or _is_prefix(l_sing, a_sing):
        return True

    return False


def split_owners(pline_text: str) -> list:
    """Split a P-line or label string into individual owner entities.

    Handles:
    - Bracketed annotations: [dist. Tratore] → strips and optionally yields Tratore
    - Semicolons as separators
    - Slashes as separators (but NOT inside artist names with " and " or " & ")
    - " and " / " & " ONLY split when left side ends with a corporate suffix

    Returns a list of owner strings (stripped, non-empty).
    """
    if not pline_text:
        return []

    text = pline_text.strip()

    # Remove the P-line prefix: "℗ 2024 ..." or "(P) 2024 ..."
    text = re.sub(r"^[\u2117(P)]+\s*\d{4}\s*", "", text).strip()

    # Extract and remove bracketed annotations like [dist. Tratore]
    # but yield the distributor name
    bracket_names = []
    def _extract_bracket(m):
        inner = m.group(1).strip()
        # "dist. Tratore" or "dist Tratore" or "distributed by X"
        dist_match = re.match(r"(?:dist\.?|distributed\s+by)\s+(.+)", inner, re.I)
        if dist_match:
            bracket_names.append(dist_match.group(1).strip())
        return ""

    text = re.sub(r"\[([^\]]+)\]", _extract_bracket, text)
    text = text.strip()

    # Split on semicolons first
    parts = [p.strip() for p in text.split(";") if p.strip()]

    # For each part, split on " / " (slash with spaces)
    expanded = []
    for part in parts:
        expanded.extend(p.strip() for p in part.split(" / ") if p.strip())

    # For each part, conditionally split on " and " / " & "
    # Only split if the left side ends with a corporate-suffix word
    suffix_set = {_normalize(s) for s in _SUFFIXES}
    final = []
    for part in expanded:
        split_done = False
        for sep in [" and ", " & "]:
            idx = part.lower().find(sep)
            if idx > 0:
                left = part[:idx].strip()
                right = part[idx + len(sep):].strip()
                # Check if left ends with a suffix word
                left_tokens = _tokenize(left)
                if left_tokens and left_tokens[-1] in suffix_set:
                    final.append(left)
                    final.append(right)
                    split_done = True
                    break
        if not split_done:
            final.append(part)

    # Add bracket-extracted names
    final.extend(bracket_names)

    # Clean up: strip commas/periods from edges, deduplicate while preserving order
    cleaned = []
    seen = set()
    for item in final:
        item = item.strip(" ,;.:")
        if item and item.lower() not in seen:
            seen.add(item.lower())
            cleaned.append(item)

    return cleaned


def classify_label(artist: str, label: str) -> str:
    """Classify a single label string relative to an artist.

    Returns one of: 'variant', 'distributor', 'major', 'licensed', 'thirdparty'
    """
    if not label:
        return "variant"  # Empty label = no data, treat as neutral

    # Check major first (takes priority even if name matches)
    if is_major_family(label):
        return "major"

    # Check licensing clause
    if find_licensing_clause(label):
        return "licensed"

    # Check known indie
    if is_known_indie(label):
        return "thirdparty"

    # Check distributor
    if is_distributor_only(label):
        return "distributor"

    # Check name variant
    if is_name_variant(artist, label):
        return "variant"

    # Nothing matches — it's a third-party label
    return "thirdparty"
