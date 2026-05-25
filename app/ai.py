"""AI verdict generation.

Tries Groq (free tier, fast, requires API key) first.
Falls back to Gemini (free tier, requires API key).
Falls back to a deterministic rule-based verdict if no AI is available.

All calls have hard timeouts. The audit pipeline NEVER blocks on AI.
"""
from __future__ import annotations

import json

from .config import GEMINI_API_KEY, GROQ_API_KEY
from .http import post_json, get_json

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-lite:generateContent"
)

SYSTEM_PROMPT = (
    "You are a music catalog acquisitions analyst. You receive label "
    "metadata for an artist from four sources. The MOST AUTHORITATIVE "
    "source is the Apple P-line (the legal phonographic copyright "
    "string, e.g. '\u2117 2020 Russ My Way Inc. and Columbia Records'). "
    "The P-line is the ground truth: it names every owner of the master "
    "recording and any licensee the masters are licensed to.\n\n"
    "Determine whether this artist looks fully self-released across "
    "their RECENT catalog. Important rules:\n"
    "- If any P-line names a major or established indie label among the "
    "owners, FLAGGED.\n"
    "- If any P-line says 'under exclusive licence to <X>' or 'licencia "
    "exclusiva para <X>' and X is anyone other than the artist's own "
    "imprint, FLAGGED. Even if the primary owner looks self-released, "
    "a licensing-to clause means the artist does NOT control the "
    "masters and is not a buyout candidate.\n"
    "- If the P-line shows ONLY the artist or an imprint clearly named "
    "after the artist (e.g. 'Russ My Way Inc.' for Russ), CLEAN.\n"
    "- If sources disagree or P-line is missing, CAUTION.\n\n"
    "Respond in EXACTLY this format on a single line:\n"
    "<VERDICT> | <REASON>\n"
    "Where <VERDICT> is one of CLEAN, CAUTION, FLAGGED.\n"
    "<REASON> is at most 22 words, plain English. No markdown. No quotes."
)


def _user_prompt(artist: str, chartmetric: str, plines: list[str],
                 licensees: list[str], deezer: str, discogs: str,
                 rule_flag: str) -> str:
    pline_block = "\n".join(f"  - {p}" for p in plines) if plines else "  (none)"
    lic_block = ", ".join(licensees) if licensees else "(none)"
    return (
        f"Artist: {artist}\n"
        f"Chartmetric label: {chartmetric or '(none)'}\n"
        f"Apple P-line(s) (ground truth):\n{pline_block}\n"
        f"Apple 'licensed to' parties: {lic_block}\n"
        f"Deezer label(s): {deezer or '(none)'}\n"
        f"Discogs label(s): {discogs or '(none)'}\n"
        f"Rule-engine flags: {rule_flag or '(none)'}\n"
    )


def _try_groq(artist: str, chartmetric: str, plines: list[str],
              licensees: list[str], deezer: str, discogs: str,
              rule_flag: str) -> str | None:
    if not GROQ_API_KEY:
        return None
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(
                artist, chartmetric, plines, licensees, deezer, discogs,
                rule_flag)},
        ],
        "temperature": 0.1,
        "max_tokens": 90,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    data = post_json(GROQ_URL, json_body=body, headers=headers, timeout=15)
    if not data:
        return None
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return None


def _try_gemini(artist: str, chartmetric: str, plines: list[str],
                licensees: list[str], deezer: str, discogs: str,
                rule_flag: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": SYSTEM_PROMPT + "\n\n" + _user_prompt(
                artist, chartmetric, plines, licensees, deezer, discogs,
                rule_flag)}],
        }],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 90},
    }
    data = post_json(
        GEMINI_URL,
        json_body=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        timeout=15,
    )
    if not data:
        return None
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return None


def _rule_based(rule_flag: str, plines: list[str], licensees: list[str],
                deezer: str, discogs: str) -> str:
    """Last resort if no AI configured or all AI calls failed.

    The P-line drives the decision when present, since it is ground truth.
    """
    flag_upper = (rule_flag or "").upper()
    has_pline = bool(plines)

    if licensees:
        return (f"FLAGGED | P-line shows masters licensed to {licensees[0]}; "
                f"artist does not control the recording.")

    if "MAJOR" in flag_upper:
        return "FLAGGED | Major label detected. Not a self-release."
    if "INDIE" in flag_upper:
        return "FLAGGED | Established indie label detected. Not fully independent."

    if has_pline and not flag_upper:
        return "CLEAN | P-line names only artist-owned imprint across recent releases."

    if not flag_upper and not has_pline and not deezer and not discogs:
        return "CAUTION | No label data found anywhere. Manual P-line check required."

    if not flag_upper:
        return "CLEAN | All sources self-released or distributor only."

    return "CAUTION | Label diverges from artist name. Verify P-line manually."


def get_verdict(artist: str, chartmetric: str, plines: list[str],
                licensees: list[str], deezer: str, discogs: str,
                rule_flag: str) -> tuple[str, str]:
    """Return (verdict, reason). Verdict is CLEAN / CAUTION / FLAGGED."""
    raw = _try_groq(artist, chartmetric, plines, licensees, deezer, discogs,
                    rule_flag)
    if not raw:
        raw = _try_gemini(artist, chartmetric, plines, licensees, deezer,
                          discogs, rule_flag)
    if not raw:
        raw = _rule_based(rule_flag, plines, licensees, deezer, discogs)

    return _parse(raw)


def _parse(raw: str) -> tuple[str, str]:
    """Parse '<VERDICT> | <REASON>' tolerantly."""
    text = raw.strip().splitlines()[0].strip()
    if "|" in text:
        verdict, reason = text.split("|", 1)
    else:
        verdict, reason = text, ""
    verdict = verdict.strip().upper()
    reason = reason.strip()

    if "FLAGGED" in verdict:
        verdict = "FLAGGED"
    elif "CAUTION" in verdict:
        verdict = "CAUTION"
    elif "CLEAN" in verdict:
        verdict = "CLEAN"
    else:
        verdict = "CAUTION"

    if len(reason) > 240:
        reason = reason[:237] + "..."
    return verdict, reason


def is_configured() -> bool:
    return bool(GROQ_API_KEY) or bool(GEMINI_API_KEY)


def provider_name() -> str:
    if GROQ_API_KEY:
        return "Groq (llama-3.1-8b-instant)"
    if GEMINI_API_KEY:
        return "Gemini 2.5 Flash Lite"
    return "rule-based fallback"
