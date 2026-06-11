# Feature: genitractor-sources-import, Property 3: IG/FB URL normalization —
# passthrough, single-prefix, idempotence.
"""Property + example tests for genius.ig_to_url / fb_to_url.

Validates: Requirements 3.1, 3.2, 3.4, 2.6
"""
from hypothesis import given, settings, strategies as st

from app.sources.genius import ig_to_url, fb_to_url


_handle = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=40)


@settings(max_examples=200)
@given(_handle)
def test_ig_idempotent(v):
    once = ig_to_url(v)
    assert ig_to_url(once) == once


@settings(max_examples=200)
@given(_handle)
def test_fb_idempotent(v):
    once = fb_to_url(v)
    assert fb_to_url(once) == once


def test_passthrough_http():
    assert ig_to_url("https://instagram.com/foo") == "https://instagram.com/foo"
    assert ig_to_url("HTTP://x.com/y") == "HTTP://x.com/y"
    assert fb_to_url("https://facebook.com/foo") == "https://facebook.com/foo"


def test_empty_and_whitespace():
    for f in (ig_to_url, fb_to_url):
        assert f("") == ""
        assert f("   ") == ""
        assert f(None) == ""
        assert f("///") == ""
    # '@' strips to empty only for Instagram (Facebook does not strip '@').
    assert ig_to_url("@") == ""


def test_single_prefix_no_at_no_slash():
    assert ig_to_url("@foo") == "https://instagram.com/foo"
    assert ig_to_url(" foo ") == "https://instagram.com/foo"
    assert ig_to_url("/foo/") == "https://instagram.com/foo"
    assert fb_to_url("/bar/") == "https://facebook.com/bar"
    # no doubled scheme/domain
    assert ig_to_url("@foo").count("https://") == 1
    assert ig_to_url("@foo").count("instagram.com") == 1


@settings(max_examples=200)
@given(_handle)
def test_no_double_prefix(v):
    out = ig_to_url(v)
    if out and not v.strip().lower().startswith(("http://", "https://")):
        assert out.startswith("https://instagram.com/")
        assert out.count("https://instagram.com/") == 1
        assert not out[len("https://instagram.com/"):].startswith("@")
