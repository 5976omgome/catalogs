"""Shared requests.Session instances — the FD-leak fix.

Raw requests.get() creates a new connection pool per call. On macOS with
a 256 FD limit, 100+ artists × 7 calls each = crash.

Sessions reuse a single urllib3.PoolManager (default pool_connections=10,
pool_maxsize=10), so FD count stays constant regardless of artist count.
"""
import requests

# One session per source module. Each maintains its own connection pool.
itunes_session = requests.Session()
deezer_session = requests.Session()
discogs_session = requests.Session()
ai_session = requests.Session()


def close_all():
    """Call on shutdown to cleanly release sockets."""
    for s in (itunes_session, deezer_session, discogs_session, ai_session):
        try:
            s.close()
        except Exception:
            pass
