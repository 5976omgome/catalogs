"""Label classification and self-release detection."""
import re

KNOWN_MAJORS = [
    "universal", "umg", "republic", "def jam", "interscope", "capitol",
    "island", "motown", "geffen", "virgin", "polydor", "mercury",
    "sony", "smg", "columbia", "rca", "epic", "arista", "jive",
    "warner", "wmg", "atlantic", "elektra", "parlophone", "sire", "wea", "rhino",
]

KNOWN_INDIES = [
    "merlin", "beggars", "4ad", "matador", "sub pop", "secretly canadian",
    "jagjaguwar", "dead oceans", "warp", "rough trade", "domino",
    "ninja tune", "monstercat", "ingrooves", "empire", "alamo",
    "because music", "play music", "believe",
]

DISTRIBUTORS = [
    "distrokid", "tunecore", "cdbaby", "cd baby", "amuse", "landr",
    "unitedmasters", "united masters", "stem", "repost", "ditto",
    "routenote", "symphonic", "awal", "horus music", "octiive",
]

# Generic suffix words that are OK after the artist name in a self-imprint
SELF_IMPRINT_SUFFIXES = [
    "music", "records", "recordings", "recording", "productions",
    "production", "label", "ltd", "inc", "llc", "co",
]

LICENSING_MARKERS = [
    "under exclusive licen",  # english (license/licence)
    "under exclusive licens",
    "under licen",
    "under licens",
    "exclusive license to",
    "exclusive licence to",
    "licensed to",
    "licensed exclusively to",
    "licencia exclusiva",  # spanish
    "bajo licencia",
    "sous licence",  # french
    "in licenza",  # italian
    "unter lizenz",  # german
    "onder licentie",  # dutch
    "distributed by",
    "dist. by",
    "mfd by",
    "mfd. by",
]


def normalize(s: str) -> str:
    """Lowercase + strip non-alphanumeric."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def classify_label(label: str) -> str:
    """Returns 'major', 'indie', 'distributor', 'none', or 'other'."""
    if not label:
        return "none"
    ll = label.lower()
    for m in KNOWN_MAJORS:
        if m in ll:
            return "major"
    for i in KNOWN_INDIES:
        if i in ll:
            return "indie"
    for d in DISTRIBUTORS:
        if d in ll:
            return "distributor"
    return "other"


def is_distributor(label: str) -> bool:
    return classify_label(label) == "distributor"


def is_self_released(artist_name: str, label: str) -> bool:
    """
    Strict self-release check.
    True if:
      - label is empty
      - label is a known DIY distributor
      - label normalized exactly equals artist normalized
      - label normalized is artist + only known suffix words
    """
    if not label:
        return True
    if is_distributor(label):
        return True

    an = normalize(artist_name)
    ln = normalize(label)
    if not an or not ln:
        return False

    if an == ln:
        return True

    # Check artist + suffix pattern
    if ln.startswith(an):
        rest = ln[len(an):]
        if not rest:
            return True
        # Strip known suffixes one at a time
        remaining = rest
        progress = True
        while remaining and progress:
            progress = False
            for suf in SELF_IMPRINT_SUFFIXES:
                sn = normalize(suf)
                if remaining.startswith(sn):
                    remaining = remaining[len(sn):]
                    progress = True
                    break
        if not remaining:
            return True

    return False


def is_likely_self_imprint(artist_name: str, label: str) -> bool:
    """
    Self-imprint = label name contains the artist name PLUS additional words
    that look like a label imprint (Music, Records, Productions, etc.) or
    other words that aren't generic suffixes.

    Exact-match (artist name == label name) is treated as a clean self-release,
    not a self-imprint.

    Distributors are excluded.
    """
    if not label or is_distributor(label):
        return False
    an = normalize(artist_name)
    ln = normalize(label)
    if not an or len(an) < 3:
        return False
    if an == ln:
        return False
    # Either label contains artist or artist contains label, with strict-ish length
    if an in ln and len(ln) > len(an):
        return True
    return False


def find_licensee(text: str) -> str:
    """If a P-line / label contains a licensing marker, return the licensee. Else ''."""
    if not text:
        return ""
    lower = text.lower()
    for marker in LICENSING_MARKERS:
        idx = lower.find(marker)
        if idx >= 0:
            tail = text[idx + len(marker):].strip(" ,.:;-")
            # cut at next punctuation that ends a clause
            for stop in [",", ";", ".", "/"]:
                p = tail.find(stop)
                if p > 0:
                    tail = tail[:p]
            return tail.strip()
    return ""
