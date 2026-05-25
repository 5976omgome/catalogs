"""Shared HTTP session with retries and a sane User-Agent."""
from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import DEFAULT_TIMEOUT, USER_AGENT


def _session() -> requests.Session:
    s = requests.Session()
    # urllib3 1.x used `method_whitelist`, 2.x uses `allowed_methods`.
    retry_kwargs = dict(
        total=4,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        respect_retry_after_header=True,
    )
    try:
        retry = Retry(allowed_methods=("GET", "POST"), **retry_kwargs)
    except TypeError:
        retry = Retry(method_whitelist=frozenset(["GET", "POST"]), **retry_kwargs)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": USER_AGENT})
    return s


SESSION = _session()


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: float = DEFAULT_TIMEOUT) -> Any:
    """GET and parse JSON. Returns None on non-2xx after retries."""
    try:
        r = SESSION.get(url, params=params, headers=headers, timeout=timeout)
        if r.status_code >= 400:
            return None
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def post_json(url: str, *, json_body: dict, headers: dict | None = None,
              timeout: float = DEFAULT_TIMEOUT) -> Any:
    try:
        r = SESSION.post(url, json=json_body, headers=headers, timeout=timeout)
        if r.status_code >= 400:
            return None
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def polite_sleep(seconds: float) -> None:
    """Used between calls to respect public API rate limits."""
    if seconds > 0:
        time.sleep(seconds)
