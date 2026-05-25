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
    "You are a music catalog acquisitions analyst. You are given an artist "
    "and the labels reported by three sources (the Chartmetric export, "
    "Deezer's API, and Discogs). Determine whether this artist looks "
    "self-released and unsigned across their recent catalog. "
    "Respond in EXACTLY this format on a single line:\n"
    "<VERDICT> | <REASON>\n"
    "Where <VERDICT> is one of CLEAN, CAUTION, FLAGGED.\n"
    "  CLEAN = appears fully self-released, no label deals.\n"
    "  CAUTION = mixed signals or a distributor-only situation worth a manual check.\n"
    "  FLAGGED = clearly signed to a major or established indie label at any point.\n"
    "<REASON> is at most 18 words, plain English. No markdown. No quotes."
)


def _user_prompt(artist: str, chartmetric: str, deezer: str, discogs: str,
                 rule_flag: str) -> str:
    return (
        f"Artist: {artist}\n"
        f"Chartmetric label: {chartmetric or '(none)'}\n"
        f"Deezer labels: {deezer or '(none)'}\n"
        f"Discogs labels: {discogs or '(none)'}\n"
        f"Rule-based flag: {rule_flag or '(none)'}\n"
    )


def _try_groq(artist: str, chartmetric: str, deezer: str, discogs: str,
              rule_flag: str) -> str | None:
    if not GROQ_API_KEY:
        return None
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(
                artist, chartmetric, deezer, discogs, rule_flag)},
        ],
        "temperature": 0.1,
        "max_tokens": 80,
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


def _try_gemini(artist: str, chartmetric: str, deezer: str, discogs: str,
                rule_flag: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": SYSTEM_PROMPT + "\n\n" + _user_prompt(
                artist, chartmetric, deezer, discogs, rule_flag)}],
        }],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 80},
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


def _rule_based(rule_flag: str, deezer: str, discogs: str) -> str:
    """Last resort if no AI configured or all AI calls failed."""
    if not rule_flag and not deezer and not discogs:
        return "CAUTION | No data found in any source. Manual check required."
    if not rule_flag:
        return "CLEAN | All sources self-released or distributor only."
    if "MAJOR" in rule_flag.upper():
        return "FLAGGED | Major label detected in one or more sources."
    if "INDIE" in rule_flag.upper():
        return "FLAGGED | Established indie label detected. Not fully independent."
    return "CAUTION | Label diverges from artist name. Verify P-line on Spotify."


def get_verdict(artist: str, chartmetric: str, deezer: str, discogs: str,
                rule_flag: str) -> tuple[str, str]:
    """Return (verdict, reason). Verdict is CLEAN / CAUTION / FLAGGED."""
    raw = _try_groq(artist, chartmetric, deezer, discogs, rule_flag)
    if not raw:
        raw = _try_gemini(artist, chartmetric, deezer, discogs, rule_flag)
    if not raw:
        raw = _rule_based(rule_flag, deezer, discogs)

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
