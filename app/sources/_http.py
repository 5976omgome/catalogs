"""Shared requests.Session instances — the FD-leak fix.

Raw requests.get() creates a new connection pool per call. On macOS with
a 256 FD limit, 100+ artists × 7 calls each = crash.

Sessions reuse a single urllib3.PoolManager. We mount a custom adapter
with a larger pool (pool_connections=20, pool_maxsize=20) to handle
concurrent requests across multiple CSVs without bottlenecking.
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Larger pool to handle 4 CSVs × 4 parallel artists = up to 16 concurrent requests
_POOL_CONNECTIONS = 20
_POOL_MAXSIZE = 20

# Retry only on connection errors and 429/503, with short backoff
_RETRY = Retry(
    total=1,
    backoff_factor=0.3,
    status_forcelist=[429, 503],
    allowed_methods=["GET"],
    raise_on_status=False,
)


def _make_session() -> requests.Session:
    """Create a session with a larger connection pool to avoid bottlenecks."""
    s = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=_POOL_CONNECTIONS,
        pool_maxsize=_POOL_MAXSIZE,
        max_retries=_RETRY,
    )
    s.mount("https://", adapter)
    s.mount("http://", adapter)
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
