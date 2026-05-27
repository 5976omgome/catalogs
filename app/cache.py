"""Tiny SQLite-backed cache so re-runs are instant. Keyed by (source, artist).
A miss returns None; a known-empty result returns an empty list (sentinel)
so we don't re-hit the network for artists genuinely missing from a source."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Optional

from . import config

_LOCK = threading.Lock()
_DB_PATH = config.CACHE_DIR / "cache.db"
_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache "
        "(source TEXT, key TEXT, value TEXT, ts INTEGER, PRIMARY KEY (source, key))"
    )
    return conn


def get(source: str, key: str) -> Optional[Any]:
    with _LOCK:
        with _conn() as conn:
            row = conn.execute(
                "SELECT value, ts FROM cache WHERE source = ? AND key = ?",
                (source, key),
            ).fetchone()
    if not row:
        return None
    value_json, ts = row
    if time.time() - ts > _TTL_SECONDS:
        return None
    try:
        return json.loads(value_json)
    except Exception:
        return None


def put(source: str, key: str, value: Any) -> None:
    payload = json.dumps(value)
    now = int(time.time())
    with _LOCK:
        with _conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (source, key, value, ts) "
                "VALUES (?, ?, ?, ?)",
                (source, key, payload, now),
            )
            conn.commit()
