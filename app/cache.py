"""SQLite-backed cache for label lookups.

Keyed by (source, artist_name). Stores the raw JSON-serializable payload
returned by the source so re-runs are instant and free.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .config import CACHE_DB

_DDL = """
CREATE TABLE IF NOT EXISTS label_cache (
    source       TEXT NOT NULL,
    artist_key   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    fetched_at   REAL NOT NULL,
    PRIMARY KEY (source, artist_key)
);
"""

_LOCK = threading.Lock()
# 30 days
DEFAULT_TTL = 30 * 24 * 60 * 60


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_DB, check_same_thread=False)
    conn.execute(_DDL)
    return conn


def _key(artist: str) -> str:
    return artist.strip().lower()


def get(source: str, artist: str, ttl: int = DEFAULT_TTL) -> Any | None:
    with _LOCK, _conn() as c:
        row = c.execute(
            "SELECT payload, fetched_at FROM label_cache WHERE source=? AND artist_key=?",
            (source, _key(artist)),
        ).fetchone()
    if not row:
        return None
    payload, fetched_at = row
    if time.time() - fetched_at > ttl:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def put(source: str, artist: str, payload: Any) -> None:
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO label_cache (source, artist_key, payload, fetched_at) "
            "VALUES (?,?,?,?)",
            (source, _key(artist), json.dumps(payload), time.time()),
        )
        c.commit()


def clear() -> int:
    with _LOCK, _conn() as c:
        cur = c.execute("DELETE FROM label_cache")
        c.commit()
        return cur.rowcount
