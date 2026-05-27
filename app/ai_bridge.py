"""
AI label-bridge: narrowly scoped tiebreaker for trivial label-string differences.

Only called when the rule engine flagged ONLY for DIVERGES reasons.
Cannot override MAJOR / INDIE / LICENSED-TO / OLD_CATALOG / SELF_IMPRINT.
Falls back to deterministic loose-string compare if no API key is set.
"""
import threading
from typing import List

import requests

from .config import GROQ_API_KEY, GEMINI_API_KEY
from .labels import normalize, is_distributor, SELF_IMPRINT_SUFFIXES

_PROMPT_TMPL = (
    "You are a music catalog analyst. Decide if these label strings refer "
    "to the same self-released entity for artist '{artist}'. Account for "
    "whitespace, punctuation, abbreviation differences (e.g. 'X Records' "
    "vs 'X Recordings'). Labels found:\n{labels}\n\n"
    "Answer with exactly one word: YES or NO. "
    "YES only if every label is either the artist name (with optional "
    "generic suffix like Music/Records) or a known DIY distributor. "
    "NO if any label looks like a third-party imprint or major/indie label."
)


def _format_labels(labels: List[str]) -> str:
    return "\n".join(f"- {l}" for l in labels if l)


def _call_groq(prompt: str, timeout: float = 12.0) -> str:
    if not GROQ_API_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
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
    if not GEMINI_API_KEY:
        return ""
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
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
    Returns True if every label is plausibly the artist (with optional suffix)
    or a known distributor.
    """
    an = normalize(artist)
    if not an:
        return False
    for label in labels:
        if not label:
            continue
        if is_distributor(label):
            continue
        ln = normalize(label)
        if ln == an:
            continue
        # Artist + suffix pattern
        if ln.startswith(an):
            rest = ln[len(an):]
            ok = True
            while rest and ok:
                ok = False
                for suf in SELF_IMPRINT_SUFFIXES:
                    sn = normalize(suf)
                    if rest.startswith(sn):
                        rest = rest[len(sn):]
                        ok = True
                        break
            if not rest:
                continue
        # Loose containment with high similarity
        if an in ln and len(ln) - len(an) <= 12:
            continue
        return False
    return True


def bridge_diverges(artist: str, labels: List[str]) -> bool:
    """
    Returns True if the AI thinks all the divergent labels are the same
    self-released entity. False if not, or if AI unavailable and fallback
    can't confirm.
    """
    labels = [l for l in labels if l]
    if not labels:
        return True

    prompt = _PROMPT_TMPL.format(artist=artist, labels=_format_labels(labels))

    result = [None]

    def _try():
        # Try Groq first
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
        # Ambiguous response, fall through to deterministic

    return _deterministic_bridge(artist, labels)
