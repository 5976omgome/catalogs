"""Shared requests.Session factory. One Session per source module means
one urllib3 connection pool per host, which means a small bounded number of
file descriptors regardless of how many artists we audit. This fixes the
[Errno 24] Too many open files crash on macOS (default ulimit -n is 256).
"""
from __future__ import annotations

import threading
from typing import Dict

import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    Retry = None  # type: ignore

_LOCK = threading.Lock()
_SESSIONS: Dict[str, requests.Session] = {}


def session(name: str) -> requests.Session:
    """Returns a shared, pooled Session keyed by `name`. Idempotent."""
    with _LOCK:
        s = _SESSIONS.get(name)
        if s is not None:
            return s
        s = requests.Session()
        # Cap concurrent connections per host. Connection reuse is automatic.
        adapter_kwargs = {
            "pool_connections": 4,
            "pool_maxsize": 8,
            "pool_block": False,
        }
        if Retry is not None:
            adapter_kwargs["max_retries"] = Retry(
                total=2,
                backoff_factor=0.3,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST"]),
                respect_retry_after_header=True,
            )
        adapter = HTTPAdapter(**adapter_kwargs)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSIONS[name] = s
        return s


def close_all() -> None:
    """Closes every Session and its underlying connection pools.
    Useful at process shutdown or between test runs.
    """
    with _LOCK:
        for s in _SESSIONS.values():
            try:
                s.close()
            except Exception:
                pass
        _SESSIONS.clear()
