"""Excel writer + filtered re-export.

CRITICAL: openpyxl Workbook objects do NOT close their underlying zip
file when they go out of scope (their `__del__` doesn't always run
on macOS), so we always call wb.close() in a finally block. This is
the file-descriptor leak that produced the [Errno 24] crash on the
user's previous build.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Display column order (extras from the input CSV are appended after these)
PRIMARY_COLS: List[str] = [
    "Artist",
    "Spotify Links",
    "Genres",
    "Region",
    "Spotify Monthly Listeners",
    "Associated Labels",
    "Recent Momentum",
    "Status",
    "Status Reason",
    "iTunes P-Line",
    "Licensee",
    "Earliest Year",
    "Earliest Year Note",
    "Label Evaluations",
    "AI / Informational",
    "Verdict",   # CLEAN/FLAGGED for backward compat
]

# Row colors keyed by Status
_FILL_KEEP = PatternFill("solid", start_color="D5F0DC", end_color="D5F0DC")
_FILL_REVIEW = PatternFill("solid", start_color="FFF2CC", end_color="FFF2CC")
_FILL_DROP = PatternFill("solid", start_color="F8D7DA", end_color="F8D7DA")
_FILL_HEADER = PatternFill("solid", start_color="1DB954", end_color="1DB954")
_FILL_ZEBRA = PatternFill("solid", start_color="F4F4F4", end_color="F4F4F4")

_BORDER = Border(
    left=Side(style="thin", color="DDDDDD"),
    right=Side(style="thin", color="DDDDDD"),
    top=Side(style="thin", color="DDDDDD"),
    bottom=Side(style="thin", color="DDDDDD"),
)


def _fill_for_status(status: str) -> Optional[PatternFill]:
    if status == "KEEP":
        return _FILL_KEEP
    if status == "REVIEW":
        return _FILL_REVIEW
    if status and status.startswith("DROP"):
        return _FILL_DROP
    return None


def _ordered_columns(df: pd.DataFrame) -> List[str]:
    cols = [c for c in PRIMARY_COLS if c in df.columns]
    extras = [c for c in df.columns if c not in cols]
    return cols + extras


def write_xlsx(df: pd.DataFrame, path: Path) -> None:
    """Writes the dataframe to `path` with KEEP/REVIEW/DROP_* row coloring.
    Always closes the workbook afterward.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook(write_only=False)
    try:
        ws = wb.active
        ws.title = "Audit"
        cols = _ordered_columns(df)

        # Header
        for j, col in enumerate(cols, start=1):
            cell = ws.cell(row=1, column=j, value=col)
            cell.font = Font(bold=True, color="FFFFFF", size=11)
            cell.fill = _FILL_HEADER
            cell.alignment = Alignment(vertical="center", horizontal="center")
            cell.border = _BORDER

        # Body
        spotify_col_idx = (cols.index("Spotify Links") + 1) if "Spotify Links" in cols else None
        for i, (_, row) in enumerate(df.iterrows(), start=2):
            status = str(row.get("Status", "")).strip()
            fill = _fill_for_status(status)
            if fill is None and i % 2 == 0:
                fill = _FILL_ZEBRA
            for j, col in enumerate(cols, start=1):
                val = row.get(col, "")
                if pd.isna(val):
                    val = ""
                cell = ws.cell(row=i, column=j, value=val)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = _BORDER
                if fill:
                    cell.fill = fill
                if spotify_col_idx and j == spotify_col_idx and isinstance(val, str) and val.startswith("http"):
                    cell.hyperlink = val
                    cell.font = Font(color="0066CC", underline="single")

        # Column widths
        widths = {
            "Artist": 22, "Spotify Links": 38, "Genres": 28, "Region": 14,
            "Spotify Monthly Listeners": 14, "Associated Labels": 22,
            "Recent Momentum": 13, "Status": 16, "Status Reason": 50,
            "iTunes P-Line": 40, "Licensee": 28, "Earliest Year": 12,
            "Earliest Year Note": 32, "Label Evaluations": 60,
            "AI / Informational": 50, "Verdict": 11,
        }
        for j, col in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(j)].width = widths.get(col, 18)

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{ws.max_row}"
        wb.save(str(path))
    finally:
        wb.close()


def filter_xlsx_by_status(src: Path, dst: Path, statuses: Iterable[str]) -> int:
    """Reads `src`, keeps rows whose Status column is in `statuses`,
    writes to `dst`. Returns the number of rows kept.
    Always closes both workbooks.
    """
    wanted = set(s.upper() for s in statuses)
    src_wb = load_workbook(str(src), read_only=True, data_only=True)
    try:
        ws = src_wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = list(next(rows_iter))
        except StopIteration:
            return 0
        if "Status" not in header:
            return 0
        status_idx = header.index("Status")
        kept_rows: List[List[object]] = []
        for row in rows_iter:
            row = list(row)
            status = str(row[status_idx] or "").upper()
            ok = False
            for w in wanted:
                if w == "DROP":
                    if status.startswith("DROP"):
                        ok = True
                        break
                elif w == "ALL":
                    ok = True
                    break
                elif status == w:
                    ok = True
                    break
            if ok:
                kept_rows.append(row)
    finally:
        src_wb.close()

    out_wb = Workbook()
    try:
        out_ws = out_wb.active
        out_ws.title = "Audit"
        for j, name in enumerate(header, start=1):
            cell = out_ws.cell(row=1, column=j, value=name)
            cell.font = Font(bold=True, color="FFFFFF", size=11)
            cell.fill = _FILL_HEADER
            cell.alignment = Alignment(vertical="center", horizontal="center")
            cell.border = _BORDER
        for i, row in enumerate(kept_rows, start=2):
            status = str(row[status_idx] or "").strip()
            fill = _fill_for_status(status)
            if fill is None and i % 2 == 0:
                fill = _FILL_ZEBRA
            for j, val in enumerate(row, start=1):
                cell = out_ws.cell(row=i, column=j, value=val if val is not None else "")
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = _BORDER
                if fill:
                    cell.fill = fill
        if header:
            out_ws.freeze_panes = "A2"
            out_ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{out_ws.max_row}"
        # widths — copy from src by index
        widths = {
            "Artist": 22, "Spotify Links": 38, "Genres": 28, "Region": 14,
            "Spotify Monthly Listeners": 14, "Associated Labels": 22,
            "Recent Momentum": 13, "Status": 16, "Status Reason": 50,
            "iTunes P-Line": 40, "Licensee": 28, "Earliest Year": 12,
            "Earliest Year Note": 32, "Label Evaluations": 60,
            "AI / Informational": 50, "Verdict": 11,
        }
        for j, col in enumerate(header, start=1):
            out_ws.column_dimensions[get_column_letter(j)].width = widths.get(col, 18)
        dst.parent.mkdir(parents=True, exist_ok=True)
        out_wb.save(str(dst))
    finally:
        out_wb.close()
    return len(kept_rows)
