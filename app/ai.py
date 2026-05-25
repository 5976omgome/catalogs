"""AI bridge for cross-source label disambiguation.

The AI here has ONE narrow job: when iTunes / Deezer / Discogs / Chartmetric
all agree the label is the artist's own name (or a known DIY distributor)
but the rule engine says they 'diverge' because of trivial string
differences (whitespace, punctuation, abbreviations like 'Records' vs
'Recordings'), the AI confirms the labels really are the same entity and
allows the verdict to flip from FLAGGED -> CLEAN.

The AI NEVER overrides:
  - MAJOR / INDIE label hits
  - LICENSED-TO clauses (masters licensed to a third party)
  - SELF_IMPRINT detections (creative-named imprints like 'OVO' or 'DIEMON'
    always stay flagged for manual review)
  - OLD_CATALOG flags (pre-2005 first-release year)

Provider order: Groq -> Gemini -> deterministic fallback.
All calls have hard timeouts; the audit pipeline never blocks on AI.
"""
from __future__ import annotations

import re

from .config import GEMINI_API_KEY, GROQ_API_KEY
from .http import post_json

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-lite:generateContent"
)


SYSTEM_PROMPT = (
    "You are checking whether a list of record-label strings, pulled from "
    "different music databases for the SAME artist, all refer to the same "
    "self-release entity (i.e. the artist themselves or a known DIY "
    "distributor like DistroKid / CD Baby / TuneCore).\n\n"
    "You are NOT asked to evaluate label history, signing status, or "
    "licensing. You ARE asked to ignore trivial string differences:\n"
    "  - whitespace and punctuation\n"
    "  - capitalisation\n"
    "  - 'Records' vs 'Recordings' vs 'Music' vs 'Productions' vs 'Inc' / "
    "'LLC' / 'Ltd' / 'Group'\n"
    "  - articles ('The X' vs 'X')\n"
    "  - obvious abbreviations\n\n"
    "Reply EXACTLY one line in this format:\n"
    "<MATCH|MIXED> | <REASON, max 18 words>\n\n"
    "MATCH = every label string clearly refers to the artist's own "
    "self-release entity, or a DIY distributor.\n"
    "MIXED = at least one label looks like a different entity that the "
    "artist might be signed to (a third-party label, an imprint with a "
    "different name from the artist, anything you cannot confidently "
    "match to the artist).\n"
    "When in doubt, answer MIXED."
)


def _user_prompt(artist: str, sources: dict[str, str]) -> str:
    src_lines = []
    for name, value in sources.items():
        if value:
            src_lines.append(f"  {name}: {value}")
    body = "\n".join(src_lines) if src_lines else "  (none)"
    return (
        f"Artist: {artist}\n"
        f"Label strings reported per source:\n{body}\n"
    )


def _try_groq(artist: str, sources: dict[str, str]) -> str | None:
    if not GROQ_API_KEY:
        return None
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(artist, sources)},
        ],
        "temperature": 0.05,
        "max_tokens": 60,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    data = post_json(GROQ_URL, json_body=body, headers=headers, timeout=12)
    if not data:
        return None
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return None


def _try_gemini(artist: str, sources: dict[str, str]) -> str | None:
    if not GEMINI_API_KEY:
        return None
    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": SYSTEM_PROMPT + "\n\n" + _user_prompt(artist, sources)}],
        }],
        "generationConfig": {"temperature": 0.05, "maxOutputTokens": 60},
    }
    data = post_json(
        GEMINI_URL,
        json_body=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        timeout=12,
    )
    if not data:
        return None
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return None


def _normalise_loose(s: str) -> str:
    """Strip punctuation, common label suffix words, and extra whitespace."""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    drop = {
        "records", "recordings", "music", "productions", "production",
        "studios", "studio", "media", "group", "ltd", "llc", "inc",
        "co", "company", "official", "label", "publishing", "ent",
        "entertainment",
    }
    tokens = [t for t in s.split() if t and t not in drop]
    return " ".join(tokens).strip()


def _deterministic_match(sources: dict[str, str], artist: str) -> bool:
    """Last-resort fallback when no AI is configured.

    Rule: every non-empty label, after stripping label-suffix words and
    punctuation, must equal either the loose-normalised artist name OR
    contain a known DIY distributor name.
    """
    target = _normalise_loose(artist)
    if not target:
        return False

    distributors = (
        "distrokid", "tunecore", "cd baby", "cdbaby", "amuse",
        "unitedmasters", "united masters", "ditto", "routenote",
        "landr", "stem", "awal", "the orchard",
    )

    for value in sources.values():
        for part in re.split(r"\s*\|\s*", value or ""):
            part = part.strip()
            if not part:
                continue
            low = part.lower()
            if any(d in low for d in distributors):
                continue
            if _normalise_loose(part) != target:
                return False
    return True


# ---------------------------------------------------------------------------


def is_configured() -> bool:
    return bool(GROQ_API_KEY) or bool(GEMINI_API_KEY)


def provider_name() -> str:
    if GROQ_API_KEY:
        return "Groq (llama-3.1-8b-instant)"
    if GEMINI_API_KEY:
        return "Gemini 2.5 Flash Lite"
    return "deterministic fallback"


def bridge_diverges(
    *,
    artist: str,
    itunes: str,
    deezer: str,
    discogs: str,
    chartmetric: str,
) -> tuple[bool, str]:
    """Return (is_match, reason).

    is_match=True means the AI (or deterministic fallback) is confident the
    divergent label strings all describe the same self-release entity.
    The audit pipeline only calls this when the rule engine produced
    DIVERGES-only flags.
    """
    sources = {
        "iTunes P-line owners": itunes,
        "Deezer label(s)": deezer,
        "Discogs label(s)": discogs,
        "Chartmetric Associated Labels": chartmetric,
    }

    raw = _try_groq(artist, sources) or _try_gemini(artist, sources)
    if raw:
        first_line = raw.strip().splitlines()[0].strip()
        verdict, _, reason = first_line.partition("|")
        verdict = verdict.strip().upper()
        reason = reason.strip()
        if verdict == "MATCH":
            return True, reason or "AI confirmed labels match across sources."
        if verdict == "MIXED":
            return False, reason or "AI flagged a possible third-party label."
        # Unparseable response -> fall through to deterministic.

    if _deterministic_match(sources, artist):
        return True, "Deterministic match: every label equals artist or distributor."
    return False, "Could not confirm labels are the same entity."
