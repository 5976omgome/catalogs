"""Plain-CSV export — produces .csv output with raw cell values only.

This is the CSV counterpart to ``app/excel.py``. It deliberately produces
**no** workbook/cell formatting (no colors, fonts, column widths, frozen
panes) — only a header row followed by raw data rows (clause 2.20).

It replicates the EXACT columns and the EXACT filter semantics of the
openpyxl versions in ``excel.py`` (including the ``ALL`` rule and the
``DROP*``-prefix matching) so export column/filter parity is preserved
(clause 3.3 / Property 6). Only the container format changes to CSV.

Uses Python's stdlib ``csv`` module — no openpyxl on this path.
"""
import csv
from pathlib import Path
from typing import List

import pandas as pd


def _coerce(val) -> str:
    """Match excel.write_xlsx cell coercion: None / 'nan' -> empty string."""
    if val is None:
        return ""
    s = str(val)
    if s == "nan":
        return ""
    return s


def _read_rows(path: Path):
    """Read a CSV checkpoint into (headers, data_rows) of raw strings.

    Mirrors how excel.py read xlsx rows: empty cells become "" (not NaN),
    every value is a plain string.
    """
    df = pd.read_csv(str(path), dtype=str, keep_default_na=False, na_filter=False)
    # Drop pandas' phantom unnamed index columns, mirroring the worker's read.
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    headers = list(df.columns)
    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
    return headers, rows


def write_csv(df: pd.DataFrame, path: Path):
    """Write a dataframe to a plain CSV file (header row + raw values).

    No styling of any kind — this is the intentional replacement for the
    styled xlsx writer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(df.columns)
    with open(str(path), "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([_coerce(h) for h in headers])
        for row_tuple in df.itertuples(index=False, name=None):
            writer.writerow([_coerce(v) for v in row_tuple])


def filter_csv_by_status(source_path: Path, dest_path: Path, statuses: List[str]) -> int:
    """Read an existing CSV, filter rows by Status column, write a new CSV.

    Args:
        source_path: Path to the full output CSV.
        dest_path: Path to write the filtered CSV.
        statuses: List of status values to include (e.g. ["KEEP"]).
                  Special value "ALL" includes everything.
                  Special value "DROP" includes all DROP_* variants.

    Returns:
        Number of rows kept in the filtered output.

    Replicates ``excel.filter_xlsx_by_status`` row selection exactly.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    headers, data_rows = _read_rows(source_path)
    if not headers:
        return 0

    # Find Status column
    try:
        status_idx = headers.index("Status")
    except ValueError:
        status_idx = None

    # Filter (identical semantics to excel.filter_xlsx_by_status)
    if "ALL" in statuses:
        filtered = data_rows
    elif status_idx is not None:
        filtered = []
        for row in data_rows:
            row_status = str(row[status_idx]) if row[status_idx] else ""
            if row_status in statuses:
                filtered.append(row)
            elif "DROP" in statuses and row_status.startswith("DROP"):
                filtered.append(row)
    else:
        filtered = data_rows

    if not filtered:
        return 0

    df = pd.DataFrame(filtered, columns=headers)
    write_csv(df, dest_path)
    return len(filtered)


def merge_all_csv(source_paths: list, dest_path: Path) -> Path:
    """Merge multiple output CSV files into one combined CSV.

    Reads all source files, concatenates their data rows (preserving headers
    from the first file), and writes a single plain CSV. Mirrors
    ``excel.merge_all_outputs``.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    headers = None

    for src_path in source_paths:
        h, rows = _read_rows(Path(src_path))
        if not h:
            continue
        if headers is None:
            headers = h
        for row in rows:
            all_rows.append(row)

    if not headers or not all_rows:
        raise ValueError("No data rows found in any output file")

    df = pd.DataFrame(all_rows, columns=headers)
    write_csv(df, dest_path)
    return dest_path
