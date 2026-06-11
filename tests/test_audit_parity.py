# Feature: genitractor-sources-import, Property 7: Chartporter export excludes
# social columns while preserving audit field values and filter semantics.
"""Golden audit-parity test for Chartporter.

Validates: Requirements 6.1, 6.2, 7.1, 7.5, 7.6

Mocks iTunes/Deezer/AI sources to fixed responses, runs a fixed sample catalog
through audit.audit_artist, assembles the audit columns exactly as jobs.py does,
writes plain CSV via csv_export.write_csv, and compares the six audit fields
against a committed golden file. Also asserts AUDIT_COLUMNS and the produced
header contain no social columns.
"""
from pathlib import Path

import pandas as pd
import pytest

from app import audit as audit_mod, excel, csv_export
from app.sources import itunes, deezer
from app import ai_bridge


_GOLDEN = Path(__file__).resolve().parent / "golden" / "audit_baseline.csv"
_SOCIAL = {"Instagram", "Facebook", "YouTube", "Twitter"}

# Fixed sample catalog: (artist, chartmetric_label, chartmetric_year)
SAMPLE = [
    ("Major Star", "Universal Music Group", 2018),       # DROP_MAJOR (CM early-exit)
    ("Licensed Act", "under exclusive license to RCA", 2019),  # DROP_LICENSED
    ("Indie Self", "Indie Self Records", 2015),           # KEEP (variant via iTunes)
    ("Third Party", "Some Random Label", 2016),           # DROP_THIRDPARTY
    ("No Data", "", None),                                 # REVIEW (no data)
]

# Per-artist mocked source releases (only used for non-early-exit artists).
ITUNES_RELEASES = {
    "Indie Self": [{"label": "Indie Self Records", "title": "Album", "year": 2015,
                    "copyright_raw": "(P) 2015 Indie Self Records"}],
    "Third Party": [{"label": "Big Third Party Co", "title": "Track", "year": 2016,
                     "copyright_raw": "(P) 2016 Big Third Party Co"}],
}


@pytest.fixture
def mocked_sources(monkeypatch):
    monkeypatch.setattr(itunes, "get_releases", lambda a: ITUNES_RELEASES.get(a, []))
    monkeypatch.setattr(deezer, "get_releases", lambda a: [])
    monkeypatch.setattr(itunes, "get_earliest_year", lambda a: None)
    monkeypatch.setattr(deezer, "get_earliest_year", lambda a: None)
    monkeypatch.setattr(ai_bridge, "bridge_check", lambda artist, labels_by_source: "")


def _build_df():
    """Run the audit and assemble audit columns exactly like jobs._audit_one."""
    rows = []
    for artist, cm_label, cm_year in SAMPLE:
        a = audit_mod.audit_artist(artist=artist, chartmetric_label=cm_label,
                                   chartmetric_first_year=cm_year)
        itunes_labels, deezer_labels = [], []
        for ev in a.evaluations:
            entry = f"{ev.label} [{ev.classification}]"
            if ev.source == "iTunes":
                itunes_labels.append(entry)
            elif ev.source == "Deezer":
                deezer_labels.append(entry)
        rows.append({
            "Artist": artist,
            "Status": str(a.status),
            "Status Reason": str(a.status_reason),
            "iTunes Labels": " | ".join(itunes_labels),
            "Deezer Labels": " | ".join(deezer_labels),
            "Earliest Year": str(a.earliest_year or ""),
            "AI Note": str(a.ai_note),
        })
    cols = ["Artist"] + excel.AUDIT_COLUMNS
    return pd.DataFrame(rows, columns=cols)


def test_audit_columns_have_no_socials():
    assert excel.AUDIT_COLUMNS == [
        "Status", "Status Reason", "iTunes Labels",
        "Deezer Labels", "Earliest Year", "AI Note",
    ]
    assert not (_SOCIAL & set(excel.AUDIT_COLUMNS))


def test_audit_parity_golden(mocked_sources, tmp_path):
    df = _build_df()
    out = tmp_path / "out.csv"
    csv_export.write_csv(df, out)

    written = pd.read_csv(out, dtype=str, keep_default_na=False, na_filter=False)
    # No social columns leak into the output header.
    assert not (_SOCIAL & set(written.columns))

    if not _GOLDEN.exists():
        _GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        csv_export.write_csv(df, _GOLDEN)
        pytest.skip("Generated audit golden baseline; re-run to compare.")

    golden = pd.read_csv(_GOLDEN, dtype=str, keep_default_na=False, na_filter=False)
    # Byte-for-byte parity of the six audit fields + artist key.
    pd.testing.assert_frame_equal(written, golden)
