"""AI bridge — informational only under the new spec.

Given a row that the rule engine is about to drop for THIRDPARTY-only reasons,
the bridge can add a short note ('AI agreed: BerkMusic is unrelated to Monique
Smit'), but it CANNOT promote a DROP to KEEP.

Uses the shared pooled Session so it doesn't leak file descriptors.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .sources import _http


def _session():
    return _http.session("ai")


def _try_groq(prompt: str) -> Optional[str]:
    key = config.groq_api_key()
    if not key:
        return None
    s = _session()
    try:
        r = s.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system",
                     "content": "You answer in one short sentence."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 80,
                "temperature": 0.1,
            },
            timeout=12,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return None


def _try_gemini(prompt: str) -> Optional[str]:
    key = config.gemini_api_key()
    if not key:
        return None
    s = _session()
    try:
        r = s.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 80, "temperature": 0.1},
            },
            timeout=12,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or [{}]
        return (parts[0].get("text") or "").strip()
    except Exception:
        return None


def informational_note(artist: str, evaluations) -> str:
    """Returns a one-sentence informational note. Never gates the verdict.
    Empty string if no LLM available."""
    if not evaluations:
        return ""
    third = [e for e in evaluations if e.get("classification") == "thirdparty"]
    if not third:
        return ""
    summary = ", ".join(f"{e['source']}={e['label']}" for e in third)
    prompt = (
        f"Artist '{artist}' has these third-party label hits: {summary}. "
        f"In one short sentence, do they look like the artist's own imprint "
        f"(say 'maybe own imprint') or unrelated labels (say 'unrelated')?"
    )
    out = _try_groq(prompt) or _try_gemini(prompt)
    if not out:
        return ""
    # cap length
    return out.split("\n")[0][:200]
