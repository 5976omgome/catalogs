"""Tiny SQLite cache for API lookups, 30-day TTL."""
import json
import sqlite3
import time
from typing import Any, Optional

from .config import CACHE_DIR

_DB = CACHE_DIR / "cache.db"
_TTL_SECONDS = 30 * 24 * 60 * 60
_MISS = object()


def _conn():
    c = sqlite3.connect(str(_DB))
    c.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "  k TEXT PRIMARY KEY, v TEXT NOT NULL, ts INTEGER NOT NULL"
        ")"
    )
    return c


def get(key: str) -> Any:
    """Returns cached value, or _MISS sentinel if absent/expired."""
    try:
        with _conn() as c:
            row = c.execute("SELECT v, ts FROM cache WHERE k = ?", (key,)).fetchone()
            if not row:
                return _MISS
            v, ts = row
            if time.time() - ts > _TTL_SECONDS:
                return _MISS
            return json.loads(v)
    except Exception:
        return _MISS


def set_(key: str, value: Any) -> None:
    try:
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO cache (k, v, ts) VALUES (?, ?, ?)",
                (key, json.dumps(value), int(time.time())),
            )
    except Exception:
        pass


def is_miss(value: Any) -> bool:
    return value is _MISS
