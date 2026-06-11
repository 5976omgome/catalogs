# Feature: genitractor-sources-import, Property 7: filter selection is
# independent of non-Status columns; ALL/DROP semantics; None/"nan" coercion.
"""Tests csv_export filter parity and coercion.

Validates: Requirements 7.2, 7.3, 7.4, 10.9
"""
import pandas as pd
from hypothesis import given, settings, strategies as st

from app import csv_export

_STATUSES = ["KEEP", "REVIEW", "DROP_MAJOR", "DROP_LICENSED", "DROP_THIRDPARTY"]


def _write(tmp_path, statuses, extra_cols=0):
    rows = []
    for i, s in enumerate(statuses):
        row = {"Artist": f"A{i}", "Status": s, "Status Reason": f"r{i}"}
        for c in range(extra_cols):
            row[f"Extra{c}"] = f"v{i}_{c}"
        rows.append(row)
    df = pd.DataFrame(rows)
    src = tmp_path / "src.csv"
    csv_export.write_csv(df, src)
    return src


def test_all_selects_every_row(tmp_path):
    src = _write(tmp_path, _STATUSES)
    dst = tmp_path / "all.csv"
    assert csv_export.filter_csv_by_status(src, dst, ["ALL"]) == len(_STATUSES)


def test_drop_prefix_matches_all_drop_variants(tmp_path):
    src = _write(tmp_path, _STATUSES)
    dst = tmp_path / "drop.csv"
    kept = csv_export.filter_csv_by_status(src, dst, ["DROP"])
    assert kept == 3
    out = pd.read_csv(dst, dtype=str, keep_default_na=False, na_filter=False)
    assert all(s.startswith("DROP") for s in out["Status"])


@settings(max_examples=100)
@given(statuses=st.lists(st.sampled_from(_STATUSES), min_size=1, max_size=12),
       extra=st.integers(min_value=0, max_value=4))
def test_filter_independent_of_other_columns(tmp_path_factory, statuses, extra):
    tmp = tmp_path_factory.mktemp("p")
    src_plain = _write(tmp / "a", statuses, extra_cols=0) if False else None
    # Build with and without extra columns; selection count must match.
    rows = [{"Artist": f"A{i}", "Status": s} for i, s in enumerate(statuses)]
    df0 = pd.DataFrame(rows)
    rows_x = [dict(r, **{f"E{c}": "z" for c in range(extra)}) for r in rows]
    dfx = pd.DataFrame(rows_x)
    p0, px = tmp / "p0.csv", tmp / "px.csv"
    csv_export.write_csv(df0, p0)
    csv_export.write_csv(dfx, px)
    for filt in (["KEEP"], ["REVIEW"], ["DROP"], ["ALL"]):
        n0 = csv_export.filter_csv_by_status(p0, tmp / "o0.csv", filt)
        nx = csv_export.filter_csv_by_status(px, tmp / "ox.csv", filt)
        assert n0 == nx


def test_none_and_nan_coerce_to_empty(tmp_path):
    df = pd.DataFrame([{"Artist": "A", "Status": "KEEP", "X": None},
                       {"Artist": "B", "Status": "KEEP", "X": float("nan")}])
    out = tmp_path / "c.csv"
    csv_export.write_csv(df, out)
    text = out.read_text()
    lines = text.strip().splitlines()
    # Both X values render empty.
    assert lines[1].endswith(",") and lines[2].endswith(",")
