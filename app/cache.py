"""Simple in-memory cache with TTL and max-size LRU eviction.

Avoids re-hitting APIs on re-runs. Evicts oldest entries when cache
exceeds MAX_SIZE to prevent unbounded memory growth.
"""
import time
import threading
from collections import OrderedDict
from typing import Any, Optional

_SENTINEL = object()  # Distinguishes "cached as empty" from "not cached"

_store: OrderedDict = OrderedDict()
_lock = threading.Lock()
_TTL = 60 * 60 * 24  # 24 hours
_MAX_SIZE = 5000  # Max entries before eviction


def get(key: str) -> Optional[Any]:
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.time() - ts > _TTL:
            del _store[key]
            return None
        # Move to end (most recently used)
        _store.move_to_end(key)
        if value is _SENTINEL:
            return []
        return value


def put(key: str, value: Any):
    with _lock:
        _store[key] = (value if value else _SENTINEL, time.time())
        _store.move_to_end(key)
        # Evict oldest entries if over max size
        while len(_store) > _MAX_SIZE:
            _store.popitem(last=False)


def clear():
    with _lock:
        _store.clear()
