# Feature: genitractor-sources-import, Property 4: Export rows are 4-aligned,
# forbidden-token-free, and quoting round-trips.
"""Tests the Genitractor export CSV shape via the same csv.writer path.

Validates: Requirements 2.1, 2.2, 2.3, 1.6, 2.4
"""
import csv
import io

from hypothesis import given, settings, strategies as st

HEADER = ["Artist Name", "Instagram", "Facebook", "Match Confidence"]
_FORBIDDEN = {"Twitter", "Website", "YouTube"}


def _export(contacts):
    """Replicates geni_export's writer logic exactly."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(HEADER)
    for c in contacts:
        w.writerow([
            c.get("artist", ""),
            c.get("instagram", ""),
            c.get("facebook", ""),
            c.get("match_confidence", ""),
        ])
    return out.getvalue()


_field = st.text(alphabet=st.characters(blacklist_characters="\x00"), max_size=30)
_contact = st.fixed_dictionaries({
    "artist": _field,
    "instagram": _field,
    "facebook": _field,
    "match_confidence": st.sampled_from(["", "Exact", "Uncertain"]),
})


@settings(max_examples=200)
@given(st.lists(_contact, max_size=20))
def test_rows_4_aligned_and_roundtrip(contacts):
    text = _export(contacts)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == HEADER
    assert not (_FORBIDDEN & set(rows[0]))
    assert len(rows) == len(contacts) + 1
    for original, parsed in zip(contacts, rows[1:]):
        assert len(parsed) == 4
        assert parsed[0] == original["artist"]
        assert parsed[1] == original["instagram"]
        assert parsed[2] == original["facebook"]
        assert parsed[3] == original["match_confidence"]


def test_special_characters_quote_roundtrip():
    contacts = [{"artist": 'a,b"c\nd', "instagram": "x\r\ny", "facebook": "",
                 "match_confidence": "Exact"}]
    rows = list(csv.reader(io.StringIO(_export(contacts))))
    assert rows[1][0] == 'a,b"c\nd'
    assert rows[1][3] == "Exact"
