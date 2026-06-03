"""AI Bridge — narrow LLM helper for whitespace/punctuation disambiguation.

Called ONLY when the rule engine produced DIVERGES-only flags (no MAJOR,
LICENSED, or clear THIRDPARTY). The AI answers one question:

  "Are these label strings the same entity, accounting for whitespace,
   punctuation, and abbreviation differences?"

If yes → verdict can be upgraded to KEEP.
If no or unavailable → verdict stays as-is.

AI CANNOT override: MAJOR, LICENSED, THIRDPARTY (when unambiguous).
AI CANNOT clear self-imprints.

Uses Groq (fast, free tier) → Gemini (fallback) → deterministic (final fallback).
All with hard timeouts via the shared Session.
"""
from typing import Optional
from app.sources._http import ai_session as _s
from app import config


def bridge_check(artist: str, labels_by_source: dict) -> Optional[str]:
    """Ask the AI if divergent labels are just formatting differences.

    Args:
        artist: The artist name
        labels_by_source: dict like {"iTunes": ["X Records"], "Deezer": ["X Rec."]}

    Returns:
        A short explanation string if AI confirms they're the same entity
        (e.g., "AI: bridged whitespace/punct differences"),
        or None if AI disagrees or is unavailable.
    """
    # Build a concise prompt
    source_lines = []
    for src, labels in labels_by_source.items():
        if labels:
            source_lines.append(f"{src}: {', '.join(labels)}")

    if not source_lines:
        return None

    prompt = (
        f"Music label analyst. Artist: '{artist}'. "
        f"Labels found across platforms:\n"
        + "\n".join(f"  {line}" for line in source_lines)
        + "\n\n"
        f"Question: Are ALL these labels the same entity as the artist "
        f"'{artist}' (just with whitespace, punctuation, abbreviation, "
        f"or corporate-suffix differences like 'Records' vs 'Rec.')?\n"
        f"Answer ONLY 'YES' or 'NO' followed by max 10 words explanation."
    )

    # Try Groq first
    response = _try_groq(prompt)
    if response is None:
        response = _try_gemini(prompt)

    if response is None:
        # Deterministic fallback: can't confirm, leave verdict unchanged
        return None

    # Parse response
    resp_upper = response.strip().upper()
    if resp_upper.startswith("YES"):
        return "AI: bridged whitespace/punct differences"

    return None


def _try_groq(prompt: str) -> Optional[str]:
    """Call Groq's free API with a hard timeout."""
    key = config.groq_api_key()
    if not key:
        return None

    try:
        r = _s.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 30,
                "temperature": 0.1,
            },
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=12,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


def _try_gemini(prompt: str) -> Optional[str]:
    """Call Google Gemini API as fallback."""
    key = config.gemini_api_key()
    if not key:
        return None

    try:
        r = _s.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 30, "temperature": 0.1},
            },
            headers={"Content-Type": "application/json"},
            timeout=12,
        )
        if r.status_code == 200:
            parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
    except Exception:
        pass
    return None
