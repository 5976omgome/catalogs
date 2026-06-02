"""Tiny SQLite cache for API lookups.

TTL policy:
  - Positive results (non-empty): 30 days
  - Empty/negative results ([], "", None): 24 hours

The shorter TTL for empty results means that after code fixes loosen the
matching logic, artists that were previously "not found" will be re-queried
within a day rather than staying stuck as empty for a month.
"""
import json
import sqlite3
import time
from typing import Any, Optional

from .config import CACHE_DIR

_DB = CACHE_DIR / "cache.db"
_TTL_POSITIVE = 30 * 24 * 60 * 60   # 30 days for real data
_TTL_NEGATIVE = 24 * 60 * 60        # 24 hours for empty results
_MISS = object()


def _conn():
    c = sqlite3.connect(str(_DB))
    c.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "  k TEXT PRIMARY KEY, v TEXT NOT NULL, ts INTEGER NOT NULL"
        ")"
    )
    return c


def _is_empty_value(value: Any) -> bool:
    """Check if a cached value represents an empty/negative result."""
    if value is None:
        return True
    if value == [] or value == "" or value == {}:
        return True
    return False


def get(key: str) -> Any:
    """Returns cached value, or _MISS sentinel if absent/expired."""
    try:
        with _conn() as c:
            row = c.execute("SELECT v, ts FROM cache WHERE k = ?", (key,)).fetchone()
            if not row:
                return _MISS
            v, ts = row
            parsed = json.loads(v)
            # Use shorter TTL for empty/negative results
            ttl = _TTL_NEGATIVE if _is_empty_value(parsed) else _TTL_POSITIVE
            if time.time() - ts > ttl:
                return _MISS
            return parsed
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


def clear_all() -> int:
    """Delete all cached entries. Returns count of rows deleted."""
    try:
        with _conn() as c:
            cursor = c.execute("DELETE FROM cache")
            return cursor.rowcount
    except Exception:
        return 0


def clear_empty() -> int:
    """Delete only empty/negative cached entries ([], "", null).
    This forces re-lookup of artists that previously returned no data
    without invalidating real label data we already have."""
    try:
        with _conn() as c:
            # Match JSON representations of empty values
            cursor = c.execute(
                "DELETE FROM cache WHERE v IN (?, ?, ?, ?)",
                ('[]', '""', 'null', '{}'),
            )
            return cursor.rowcount
    except Exception:
        return 0
