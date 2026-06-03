"""Simple in-memory cache with TTL. Avoids re-hitting APIs on re-runs."""
import time
from typing import Any, Optional

_SENTINEL = object()  # Distinguishes "cached as empty" from "not cached"

_store: dict = {}
_TTL = 60 * 60 * 24  # 24 hours


def get(key: str) -> Optional[Any]:
    entry = _store.get(key)
    if entry is None:
        return None
    value, ts = entry
    if time.time() - ts > _TTL:
        del _store[key]
        return None
    if value is _SENTINEL:
        return []
    return value


def put(key: str, value: Any):
    _store[key] = (value if value else _SENTINEL, time.time())


def clear():
    _store.clear()
