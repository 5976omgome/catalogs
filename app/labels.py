"""
Label classification for catalogue acquisitions.

Three primitives are exported:

    match_major_family(label)  -> (family, matched_token) or None
    is_name_variant(artist, label) -> bool
    is_neutral_distributor(label)  -> bool
    find_licensing_clause(text)    -> str  (the matched clause, '' if none)

The goal of the rewrite (vs the previous module) is that EVERY label string
returned from any platform must be one of:

    * a NAME VARIANT of the artist     (artist owns the imprint), OR
    * a NEUTRAL DISTRIBUTOR placeholder (DistroKid, recordJet, etc.), OR

...otherwise the catalogue is encumbered and we cannot license it.

The previous module flagged third-party indies with a soft "DIVERGES" marker
that the AI bridge could overrule. That produced the false CLEANs the user
hit (Jenifer Lewis -> IKONS, Charlie Hope -> Little Maple Leaf Productions,
StoryBots -> Netflix Music, etc.). The new rule engine is gated on
match_major_family + find_licensing_clause + is_name_variant /
is_neutral_distributor and CANNOT be talked out of a hard FLAG.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 1. MAJOR-FAMILY TOKEN LIST
# ---------------------------------------------------------------------------
#
# Substring match, case-insensitive, on the lowercased label string. Each
# token must be specific enough that it does not collide with a plausible
# artist or imprint name. (e.g. "sony" is OK; "republic" is OK because the
# false-positive rate on a Republic-named artist is acceptably low for our
# acquisitions use case.)
#
# Several tokens (e.g. "EUROPA", "Musica Studios") are gated by an extra
# keyword in match_major_family so they only match in major-distribution
# context, not as standalone words.

MAJOR_FAMILIES: dict[str, list[str]] = {
    "Universal": [
        "universal music", "universal records", "umg", " ume ", "ume,", "ume.",
        "polydor", "geffen", "capitol", "vertigo", "electrola", "karussell",
        "back lot music", "universal studios music", "milan records",
        "mercury records", "mercury studios", "island records", "def jam",
        "interscope", "republic records", "verve", "decca",
    ],
    "Sony": [
        "sony music", "sony entertainment", "sony classical",
        "columbia records", " rca ", "rca records", "rca,", "rca/",
        "epic records", "arista", "ariola", "hansa records", "provident",
        "nitron music", "gold league", "sevenone", "ultra music",
    ],
    "Warner": [
        "warner music", "warner records", "warner bros", "wmg", "wea",
        "atlantic records", "atlantic recording", "elektra", "parlophone",
        "rhino entertainment", "rhino records", "arts music/rhino",
        "watertower", "x5 music group", "ada worldwide", "warner chappell",
    ],
    "BMG": [
        "bmg rights management", "bmg music", "bmg entertainment",
        "bmg recorded music",
    ],
    "Disney": [
        "walt disney records", "disney music group", "hollywood records",
        "buena vista records",
    ],
    "Hasbro": [
        "hasbro",
    ],
    "Mattel": [
        "mattel - arts music", "mattel arts music", "mattel records",
    ],
    "Netflix": [  # Netflix Music acts as a major-tier owner for our purposes.
        "netflix music",
    ],
}

# Known indie labels that are still NOT name variants of any artist - used
# only by find_licensing_clause() to gate soft markers like 'distributed
# by'. Major-family detection lives in match_major_family() above.
KNOWN_INDIES: List[str] = [
    "merlin", "beggars banquet", "4ad records", "matador records",
    "sub pop", "secretly canadian", "jagjaguwar", "dead oceans",
    "warp records", "rough trade records", "domino recording",
    "ninja tune", "monstercat", "empire distribution", "alamo records",
    "because music", "play music",
]

# A few tokens are too short / too generic to substring-match safely. They
# are only flagged when they appear with a major-distribution context word
# in the same string. Format: (token, required_companion_substring or None).
# `None` companion means "match anywhere".
_GATED_MAJOR_TOKENS: list[tuple[str, Optional[str]]] = [
    # "EUROPA" alone is a German children's-music label sometimes; only flag
    # when it appears alongside Sony (e.g. "EUROPA / Sony Music Family").
    ("europa", "sony"),
    # "Musica Studios" is a Sony Indonesia subsidiary in many of our test
    # rows but is also used by independents in Spanish-speaking markets.
    ("musica studios", "sony"),
]


def match_major_family(label: str) -> Optional[Tuple[str, str]]:
    """
    Return (family_name, matched_token) if `label` belongs to a major or a
    major-equivalent rights org. Otherwise None.

    Case-insensitive substring match. Whitespace in the label is collapsed
    so multi-word tokens still hit when the label uses NBSPs or weird
    spacing.
    """
    if not label:
        return None
    text = " " + re.sub(r"\s+", " ", label.lower()).strip() + " "

    for family, tokens in MAJOR_FAMILIES.items():
        for tok in tokens:
            tok_low = tok.lower().strip()
            if not tok_low:
                continue
            # Tokens with leading/trailing space are word-boundary intentional
            # (e.g. " ume "); pass them through unchanged. Otherwise wrap.
            needle = tok if (tok.startswith(" ") or tok.endswith(" ")) else tok_low
            if needle in text:
                return (family, tok_low)

    for tok, companion in _GATED_MAJOR_TOKENS:
        if tok in text and (companion is None or companion in text):
            # Map gated tokens back to a canonical family.
            family = "Sony" if companion == "sony" else "Universal"
            return (family, tok)

    return None


# ---------------------------------------------------------------------------
# 2. NAME-VARIANT NORMALIZER
# ---------------------------------------------------------------------------
#
# A label is a "name variant" of the artist when, after stripping diacritics,
# punctuation, and corporate suffixes, the residual core matches the artist
# core via one of three rules:
#
#   (a) exact match
#   (b) artist core is a contiguous token-prefix of label core
#   (c) label core is a contiguous token-prefix of artist core
#
# The corporate-suffix list is iteratively right-stripped until no further
# suffixes can be removed. That handles "Gracie's Corner LLC" -> "Gracie's
# Corner Music" -> "Gracie's Corner" without false-positives on artists
# whose actual name happens to contain the suffix word.
#
# A LEFT-side prefix is NOT stripped. "Music for Aleksey" should not become
# "for Aleksey" by stripping "Music". That keeps "Universal Music Group"
# from collapsing to "Group" or similar nonsense.

CORPORATE_SUFFIX_TOKENS: List[str] = [
    # Order doesn't matter for correctness, but longer multi-word suffixes
    # are tried first by the stripper for greedy match.
    "music group", "record group", "music publishing",
    "rights management", "rights",
    "recordings", "recording", "records", "recordz", "rec.", "rec",
    "productions", "production",
    "entertainment", "ent.", "ent",
    "studios", "studio",
    "media", "music", "musik", "musique", "musica",
    "company", "co.", "co",
    "international", "intl.", "intl", "ltd.", "ltd",
    "llc.", "llc", "inc.", "inc", "gmbh", "s.a.", "sa",
    "s.a. de c.v.", "sa de cv",
    "pty ltd.", "pty ltd", "pty.", "pty",
    "label", "labels",
    "kids", "band",
    "oficial", "official",
    "group",
]

# Pre-sort longest-first so "music group" beats "music".
_SORTED_SUFFIX_TOKENS: List[str] = sorted(
    CORPORATE_SUFFIX_TOKENS, key=lambda s: -len(s.split())
)


def _strip_diacritics(s: str) -> str:
    """Drop combining marks: 'Türkiye' -> 'Turkiye', 'Beyoncé' -> 'Beyonce'."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _normalize_for_variant(s: str) -> str:
    """
    Lowercase, drop diacritics, replace separators with spaces, drop other
    punctuation, collapse whitespace.

    Example: "Gracie's Corner LLC" -> "gracies corner llc"
             "Lah-Lah Records"      -> "lah lah records"
    """
    if not s:
        return ""
    s = _strip_diacritics(s).lower()
    # Apostrophes and exclamation marks vanish (Gracie's -> Gracies,
    # Rockabye Baby! -> Rockabye Baby).
    s = re.sub(r"[\u2018\u2019'!?]", "", s)
    # Other punctuation/separators become spaces.
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_corporate_suffixes(core: str) -> str:
    """
    Iteratively right-strip any corporate suffix in CORPORATE_SUFFIX_TOKENS.
    The longest suffix wins per pass; passes repeat until no progress.

    "gracies corner llc" -> "gracies corner"
    "gracies corner music" -> "gracies corner"
    "lah lah records" -> "lah lah"
    "rockabye baby music" -> "rockabye baby"
    """
    if not core:
        return ""
    cur = core
    while True:
        progressed = False
        for suf in _SORTED_SUFFIX_TOKENS:
            suf_clean = _normalize_for_variant(suf)
            if not suf_clean:
                continue
            if cur == suf_clean:
                # The whole string IS just a corporate suffix. Don't let
                # "records" become an empty core; treat it as not-a-variant.
                return cur
            if cur.endswith(" " + suf_clean):
                cur = cur[: -(len(suf_clean) + 1)].rstrip()
                progressed = True
                break
        if not progressed:
            break
    return cur


def _name_core(s: str) -> str:
    """Combined normalizer: strip everything down to the comparison core."""
    return _strip_corporate_suffixes(_normalize_for_variant(s))


def _singular(token: str) -> str:
    """
    Lightweight singularizer for the LAST token of a name core.

    The spec calls out 'Nursery Rhymes' <-> 'Nursery Rhyme Productions' as a
    must-pass variant. Trim a trailing 's' (and 'es' on -shes/-ches/-xes/
    -zes) only on the last token so we don't accidentally fold 'Lewis' into
    'Lewi' or break 'Krisu'.
    """
    if not token or len(token) < 4:
        return token
    if token.endswith(("shes", "ches", "xes", "zes")):
        return token[:-2]
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _tokens_equal_loose(a: List[str], b: List[str]) -> bool:
    """Token-by-token equality, with last-token plural folding on both sides."""
    if len(a) != len(b):
        return False
    if a == b:
        return True
    if a[:-1] != b[:-1]:
        return False
    return _singular(a[-1]) == _singular(b[-1])


def is_name_variant(artist: str, label: str) -> bool:
    """
    True when `label` reads as the artist's own imprint after corporate
    suffixes are stripped from both sides.

    The three accept rules:
      (a) cores are equal (with trailing-plural tolerance on the last token)
      (b) artist core is a token-prefix of label core
      (c) label core is a token-prefix of artist core

    Token-prefix means "matches at a word boundary"; "Drake" is NOT a
    token-prefix of "Drakemount" but IS a token-prefix of "Drake Music".
    """
    if not artist or not label:
        return False

    a_core = _name_core(artist)
    l_core = _name_core(label)
    if not a_core or not l_core:
        return False

    if a_core == l_core:
        return True

    a_tokens = a_core.split()
    l_tokens = l_core.split()

    # (a') equal up to a trailing plural variation
    if _tokens_equal_loose(a_tokens, l_tokens):
        return True

    # (b) artist core is a contiguous prefix of the label core. Allow the
    # last artist token to be a singular/plural variant of the corresponding
    # label token. Without this, "Nursery Rhymes" would not prefix "Nursery
    # Rhyme Productions".
    if len(l_tokens) > len(a_tokens):
        head, last_a = l_tokens[: len(a_tokens) - 1], l_tokens[len(a_tokens) - 1]
        if head == a_tokens[:-1] and _singular(last_a) == _singular(a_tokens[-1]):
            return True

    # (c) label core is a contiguous prefix of the artist core
    if len(a_tokens) > len(l_tokens):
        head, last_l = a_tokens[: len(l_tokens) - 1], a_tokens[len(l_tokens) - 1]
        if head == l_tokens[:-1] and _singular(last_l) == _singular(l_tokens[-1]):
            return True

    # Single-token artists also accept a label whose core ENDS with the
    # artist token (handles "Music for Aleksey" / "Aleksey Music"-style
    # ordering rarely seen in iTunes copyright strings). We require the
    # match to be at a token boundary so "Aleksey" doesn't match "Drakeyy".
    if len(a_tokens) == 1 and len(l_tokens) >= 2 and l_tokens[-1] == a_tokens[0]:
        return True

    return False


# ---------------------------------------------------------------------------
# 3. NEUTRAL DISTRIBUTORS
# ---------------------------------------------------------------------------
#
# These are pure delivery / distribution placeholders that frequently appear
# as the "label" field on an otherwise self-released release. They only pass
# in the absence of a licensing clause (we still flag "DistroKid (under
# exclusive license to Republic)").
#
# Distinct from majors. A neutral distributor is fine. A major is always a
# hard FLAG even when called a "distributor".

NEUTRAL_DISTRIBUTORS: List[str] = [
    "distrokid",
    "tunecore",
    "cdbaby", "cd baby",
    "amuse",
    "landr",
    "unitedmasters", "united masters",
    "stem",
    "repost network", "repost by soundcloud",
    "ditto music",
    "routenote",
    "symphonic distribution",
    "awal",
    "horus music",
    "octiive",
    "independent",
    "recordjet",
    "igroovemusic.com", "igroovemusic",
    "imusician",
    "believe music",   # only when not paired with exclusivity language
    "mediacube music",
    "musichub",
    "tratore",
    "altafonte",
    "ingrooves",       # technically Universal-owned, but acts as a pure
                       # distributor here. If you want to disqualify, move
                       # to the majors list above.
]

# Strings of the form "1234567 Records DK" (DistroKid placeholder for
# numeric label IDs).
_NUMERIC_DISTRO_RE = re.compile(r"^\s*\d{4,}\s+records\s+dk\d?\s*$", re.I)


def is_neutral_distributor(label: str) -> bool:
    """True if the label is a pure distributor placeholder (not a major)."""
    if not label:
        return False
    if match_major_family(label) is not None:
        return False
    text = label.lower().strip()
    if _NUMERIC_DISTRO_RE.match(text):
        return True
    for needle in NEUTRAL_DISTRIBUTORS:
        if needle in text:
            return True
    return False


# ---------------------------------------------------------------------------
# 4. LICENSING-CLAUSE DETECTOR
# ---------------------------------------------------------------------------
#
# The presence of any of these phrases in a label or P-line means the
# catalogue has an existing exclusive license and is therefore encumbered.
# This is a HARD flag. The previous version had a softer threshold and the
# AI bridge could occasionally talk it out of flagging.
#
# Returns the matched clause text (everything after the marker, trimmed at
# the next punctuation that ends a clause). Empty string when no marker is
# found.

LICENSING_MARKERS: List[str] = [
    # English - hard licensing markers (these always trigger)
    "under exclusive licence to", "under exclusive license to",
    "under exclusive licence", "under exclusive license",
    "under licence to", "under license to",
    "exclusive licence to", "exclusive license to",
    "exclusively licensed to", "licensed exclusively to",
    "licensed to",
    "licensee for",
    "exclusively distributed by",
    # Spanish
    "licencia exclusiva", "bajo licencia",
    # French
    "sous licence",
    # Italian
    "in licenza",
    # German
    "unter lizenz",
    # Dutch
    "onder licentie",
]

# Soft licensing markers - "X, distributed by Y" or "X, a division of Y"
# only counts as licensing when Y names a major or known indie. Without
# that gate, "Records Inc., a division of nothing" or "12345 Records DK,
# distributed by DistroKid" would both false-flag.
SOFT_LICENSING_MARKERS: List[str] = [
    "distributed by",
    "dist. by", "dist by",
    "manufactured and distributed by", "mfd by", "mfd. by",
    "a division of",
    "a label of",
    "a subsidiary of",
]

# Sort longest-first so "under exclusive licence to" beats "exclusive".
_SORTED_LICENSING_MARKERS = sorted(LICENSING_MARKERS, key=lambda s: -len(s))
_SORTED_SOFT_LICENSING = sorted(SOFT_LICENSING_MARKERS, key=lambda s: -len(s))

# Bare "exclusively" / "exclusive" must not match harmless phrases like
# "Exclusive Records" used as a label name. Require a follow-up cue.
_BARE_EXCLUSIVE_TOKENS: set = set()  # disabled - too many false positives
_EXCLUSIVE_FOLLOW_CUES = (
    "license", "licence", "licensed", "licensee", "to ", "for ", "by ",
)


def find_licensing_clause(text: str) -> str:
    """
    Return the licensing clause if `text` contains an exclusivity / licensed-
    to marker. The returned string is the text following the marker, trimmed
    at the next clause-terminating punctuation (`,`, `;`, `.`, `/`).

    Empty string when no marker is found.

    Soft markers ('distributed by', 'a division of') only count when the
    clause names a major or known indie — that prevents false positives on
    plain prose like "Records Inc., a division of nothing" and on legit
    distributor placeholders like "12345 Records DK, distributed by
    DistroKid".
    """
    if not text:
        return ""
    lower = text.lower()

    # Hard markers always trigger.
    for marker in _SORTED_LICENSING_MARKERS:
        idx = lower.find(marker)
        if idx >= 0:
            tail = text[idx + len(marker):].strip(" ,.:;-")
            for stop in (",", ";", ".", "/"):
                p = tail.find(stop)
                if p > 0:
                    tail = tail[:p]
                    break
            return tail.strip()

    # Soft markers only trigger when the clause names a major or known indie.
    for marker in _SORTED_SOFT_LICENSING:
        idx = lower.find(marker)
        if idx < 0:
            continue
        tail = text[idx + len(marker):].strip(" ,.:;-")
        for stop in (",", ";", ".", "/"):
            p = tail.find(stop)
            if p > 0:
                tail = tail[:p]
                break
        tail = tail.strip()
        if not tail:
            continue
        # Gate: does the tail name a major or known indie? If yes, it's a
        # real licensing/distribution-by-major clause. If no, it's just
        # prose and we ignore the marker.
        if match_major_family(tail) is not None:
            return tail
        if any(needle in tail.lower() for needle in KNOWN_INDIES):
            return tail
        # No major / no indie -> not a licensing clause, just descriptive text.
        continue

    return ""


# ---------------------------------------------------------------------------
# 5. PER-LABEL EVALUATION
# ---------------------------------------------------------------------------
#
# audit.py composes these into a row-level status. Status values:
#   "MAJOR"        - hard fail, major / major-equivalent owner
#   "LICENSED"     - hard fail, exclusivity / licensed-to language
#   "VARIANT"      - pass, label is a name variant of the artist
#   "DISTRIBUTOR"  - pass, label is a neutral distributor placeholder
#   "THIRDPARTY"   - hard fail, third-party indie that isn't a name variant
#   "EMPTY"        - no label string supplied; ignored when deriving status

@dataclass
class LabelEvaluation:
    source: str            # "iTunes" | "Deezer" | "Discogs" | "Chartmetric"
    label: str             # the original label string
    status: str            # one of MAJOR / LICENSED / VARIANT / DISTRIBUTOR / THIRDPARTY / EMPTY
    reason: str            # one-line human-readable explanation
    family: str = ""       # major family if status == MAJOR
    matched_token: str = ""  # which major-token hit, when applicable
    licensee: str = ""     # licensee text when status == LICENSED


def evaluate_label(source: str, artist: str, label: str) -> LabelEvaluation:
    """
    Score a single (source, label) pair against the new spec.

    Order matters: licensing language and major-family hits ALWAYS win,
    even if the label otherwise looks like a name variant. (e.g.
    "Drake Music, distributed by Universal" must DROP_MAJOR.)
    """
    if not label or not label.strip():
        return LabelEvaluation(source=source, label="", status="EMPTY",
                               reason="no label string")

    raw = label.strip()

    # 1. Licensing language is the single highest-priority signal.
    licensee = find_licensing_clause(raw)
    if licensee:
        return LabelEvaluation(
            source=source, label=raw, status="LICENSED",
            licensee=licensee,
            reason=f"licensing clause: '...{licensee}'",
        )

    # 2. Major-family hit (substring match on full label).
    fam = match_major_family(raw)
    if fam is not None:
        family, tok = fam
        return LabelEvaluation(
            source=source, label=raw, status="MAJOR",
            family=family, matched_token=tok,
            reason=f"{family} family token '{tok}'",
        )

    # 3. Name variant of the artist? -> pass.
    if is_name_variant(artist, raw):
        return LabelEvaluation(
            source=source, label=raw, status="VARIANT",
            reason="label is name variant of artist",
        )

    # 4. Neutral distributor placeholder? -> pass.
    if is_neutral_distributor(raw):
        return LabelEvaluation(
            source=source, label=raw, status="DISTRIBUTOR",
            reason="neutral distributor placeholder",
        )

    # 5. Anything else is a third-party indie. Hard fail.
    return LabelEvaluation(
        source=source, label=raw, status="THIRDPARTY",
        reason="third-party label, not a name variant",
    )


# ---------------------------------------------------------------------------
# 6. BACKWARDS COMPATIBLE NORMALIZE
# ---------------------------------------------------------------------------
#
# Older modules (sources/itunes.py etc.) still import `normalize`; keep it
# exported with its original semantics (lowercase + strip non-alnum).

def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Backwards-compatible alias for the older name used by sources/itunes.py.
# Both functions return the licensee text after a licensing marker.
find_licensee = find_licensing_clause
