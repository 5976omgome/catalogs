"""
AI label-bridge: INFORMATIONAL-ONLY tiebreaker for label-string differences.

Behavior under the new spec (commit "rewrite classifier with name-variant
gating"): the bridge can no longer change a row's status. It is consulted
ONLY when the rule engine has already produced DROP_THIRDPARTY, and its
output is appended to ArtistAudit.informational as a note. The decision
to KEEP / DROP is the rule engine's alone.

When neither Groq nor Gemini is configured, a deterministic loose-string
compare is used; it returns True only when every label is either the
artist core (post-suffix-strip) or a known neutral distributor. This is
strictly tighter than the previous deterministic fallback.
"""
from __future__ import annotations

import threading
from typing import List

import requests

from . import config
from .labels import (
    is_name_variant,
    is_neutral_distributor,
    match_major_family,
    find_licensing_clause,
)


_PROMPT_TMPL = (
    "You are a music catalog analyst. Decide if these label strings refer "
    "to the same self-released entity for artist '{artist}'. Account for "
    "whitespace, punctuation, abbreviation differences (e.g. 'X Records' "
    "vs 'X Recordings'). Labels found:\n{labels}\n\n"
    "Answer with exactly one word: YES or NO. "
    "YES only if every label is either the artist name (with optional "
    "generic suffix like Music/Records/Productions) or a known DIY "
    "distributor (DistroKid, CD Baby, etc.). "
    "NO if any label looks like a third-party imprint, major label, or "
    "carries an exclusive-license / distributed-by clause."
)


def _format_labels(labels: List[str]) -> str:
    return "\n".join(f"- {l}" for l in labels if l)


def _call_groq(prompt: str, timeout: float = 12.0) -> str:
    key = config.groq_api_key()
    if not key:
        return ""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 10,
                "temperature": 0.0,
            },
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return ""


def _call_gemini(prompt: str, timeout: float = 12.0) -> str:
    key = config.gemini_api_key()
    if not key:
        return ""
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 10},
            },
            timeout=timeout,
        )
        if r.status_code == 200:
            cand = r.json().get("candidates", [])
            if cand:
                parts = cand[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
    except Exception:
        pass
    return ""


def _deterministic_bridge(artist: str, labels: List[str]) -> bool:
    """
    Conservative fallback when no LLM is available.
    True iff every label is a name variant or a neutral distributor AND
    none carries a licensing clause or major-family token.
    """
    for label in labels:
        if not label:
            continue
        if find_licensing_clause(label):
            return False
        if match_major_family(label):
            return False
        if is_name_variant(artist, label):
            continue
        if is_neutral_distributor(label):
            continue
        return False
    return True


def bridge_diverges(artist: str, labels: List[str]) -> bool:
    """
    Returns True if the AI thinks all the divergent labels are the same
    self-released entity. INFORMATIONAL ONLY - the caller must not change
    the row status based on this value.
    """
    labels = [l for l in labels if l]
    if not labels:
        return True

    prompt = _PROMPT_TMPL.format(artist=artist, labels=_format_labels(labels))

    result: List[str | None] = [None]

    def _try():
        r = _call_groq(prompt)
        if r:
            result[0] = r
            return
        r = _call_gemini(prompt)
        if r:
            result[0] = r

    t = threading.Thread(target=_try, daemon=True)
    t.start()
    t.join(timeout=15.0)

    if result[0]:
        ans = result[0].strip().upper()
        if ans.startswith("YES"):
            return True
        if ans.startswith("NO"):
            return False

    return _deterministic_bridge(artist, labels)
