# Feature: genitractor-sources-import, Property 5: Balanced match selection —
# exact precedence, close fallback, rejection, order, monotonicity.
"""Tests for genius.get_socials balanced top-10 artist matching.

Validates: Requirements 4.1, 4.3, 4.4, 4.5, 4.6, 4.7, 5.5
"""
import pytest
from hypothesis import given, settings, strategies as st
from hypothesis import HealthCheck

from app.sources import genius
from app.sources.genius import _normalize_name


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _install(monkeypatch, hits, artist_obj):
    """Patch genius so get_socials runs offline against the given hits."""
    monkeypatch.setattr(genius.config, "genius_token", lambda: "tok")
    store = {}
    monkeypatch.setattr(genius.cache, "get", lambda k: store.get(k))
    monkeypatch.setattr(genius.cache, "put", lambda k, v: store.__setitem__(k, v))

    def fake_request(url, params=None, headers=None, timeout=10):
        if "/search" in url:
            return _FakeResp(200, {"response": {"hits": hits}})
        # /artists/:id
        return _FakeResp(200, {"response": {"artist": artist_obj}})

    monkeypatch.setattr(genius, "_request_with_backoff", fake_request)


def _hit(name, artist_id):
    return {"result": {"primary_artist": {"id": artist_id, "name": name}}}


def test_exact_precedence_over_close(monkeypatch):
    # A close hit appears first, exact later — exact must win.
    hits = [_hit("The Weekndz", 1), _hit("The Weeknd", 2)]
    _install(monkeypatch, hits, {"instagram_name": "theweeknd", "facebook_name": ""})
    res = genius.get_socials("The Weeknd")
    assert res["match_confidence"] == "Exact"
    assert res["instagram"] == "https://instagram.com/theweeknd"


def test_close_fallback_lowest_index(monkeypatch):
    # No exact; two close hits — lowest index wins, marked Uncertain.
    hits = [_hit("Sam Smithers", 10), _hit("Sam Smith Band", 11)]
    _install(monkeypatch, hits, {"instagram_name": "@sam10", "facebook_name": ""})
    res = genius.get_socials("Sam Smith")
    assert res["match_confidence"] == "Uncertain"
    assert res["instagram"] == "https://instagram.com/sam10"


def test_reject_unrelated_including_short_prefix(monkeypatch):
    # The old 3-char-prefix code wrongly accepted "Mad..." for "Madonna".
    hits = [_hit("Mad Professor", 1), _hit("Maroon 5", 2)]
    _install(monkeypatch, hits, {"instagram_name": "x", "facebook_name": ""})
    assert genius.get_socials("Madonna") is None


def test_only_first_10_examined(monkeypatch):
    hits = [_hit("Nope %d" % i, i) for i in range(10)] + [_hit("Target", 999)]
    _install(monkeypatch, hits, {"instagram_name": "t", "facebook_name": ""})
    # "Target" is at index 10 (11th) — beyond the window → rejected.
    assert genius.get_socials("Target") is None


def test_empty_normalized_hit_guarded(monkeypatch):
    hits = [_hit("???", 1), _hit("Drake", 2)]
    _install(monkeypatch, hits, {"instagram_name": "drake", "facebook_name": ""})
    res = genius.get_socials("Drake")
    assert res["match_confidence"] == "Exact"


# --- Monotonic non-regression: balanced accepts a superset of exact-only -----
_names = st.text(alphabet="abcdefghij ", min_size=1, max_size=8)


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(query=_names, hitname=_names)
def test_monotonic_superset(query, hitname, monkeypatch):
    nq, nh = _normalize_name(query), _normalize_name(hitname)
    exact_only_accepts = bool(nq) and nq == nh
    hits = [_hit(hitname, 1)]
    _install(monkeypatch, hits, {"instagram_name": "h", "facebook_name": ""})
    res = genius.get_socials(query)
    balanced_accepts = res is not None and res is not genius.RATE_LIMITED
    # Whenever exact-only would accept, balanced must also accept.
    if exact_only_accepts:
        assert balanced_accepts
