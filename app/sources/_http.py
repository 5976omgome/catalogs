"""Shared requests.Session instances — the FD-leak fix.

Raw requests.get() creates a new connection pool per call. On macOS with
a 256 FD limit, 100+ artists × 7 calls each = crash.

Sessions reuse a single urllib3.PoolManager. We increase pool_maxsize
to handle concurrent requests across multiple CSVs without bottlenecking.

Connection pool overflow warnings are suppressed — they're harmless (the
connection is discarded and remade) but flood the terminal.
"""
import logging
import requests
from requests.adapters import HTTPAdapter

# Suppress "Connection pool is full, discarding connection" warnings
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)


class _LargePoolAdapter(HTTPAdapter):
    """HTTPAdapter with a bigger connection pool."""

    def __init__(self):
        super().__init__(pool_connections=20, pool_maxsize=20)


def _make_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", _LargePoolAdapter())
    s.mount("http://", _LargePoolAdapter())
    return s


# One session per source module. Each maintains its own connection pool.
itunes_session = _make_session()
deezer_session = _make_session()
ai_session = _make_session()


def close_all():
    """Call on shutdown to cleanly release sockets."""
    for s in (itunes_session, deezer_session, ai_session):
        try:
            s.close()
        except Exception:
            pass
