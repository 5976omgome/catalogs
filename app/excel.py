"""Excel output writer.

Three-color row palette driven by the new Status column:
    KEEP            -> green   (worth pursuing)
    REVIEW          -> yellow  (mixed signals - human eyes needed)
    DROP_*          -> red     (any DROP_MAJOR / DROP_LICENSED / DROP_THIRDPARTY)

Legacy Verdict column (CLEAN/FLAGGED) is retained for backwards compat
with any consumer that filters on it.
"""
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Order matters - this is the order the audit columns appear in the sheet
# after the input CSV columns.
AUDIT_COLS = [
    "Status",                # KEEP / REVIEW / DROP_MAJOR / DROP_LICENSED / DROP_THIRDPARTY
    "Status Reason",         # one-line plain English explanation
    "Label Evaluations",     # per-(source, label) evaluation summary
    "Verdict",               # legacy CLEAN / FLAGGED
    "Earliest Year",
    "Earliest Year Note",    # informational old-catalog note (no flag)
    "iTunes P-Line",
    "iTunes Licensee",
    "Deezer Labels",
    "Discogs Labels",
    "Informational Notes",   # AI bridge note, OLD_CATALOG note
    "Flag Reasons",          # legacy
]

_GREEN = PatternFill("solid", start_color="E6F4EA")
_YELLOW = PatternFill("solid", start_color="FFF8C5")
_RED = PatternFill("solid", start_color="FCE4E4")


def _row_fill(status: str) -> PatternFill:
    if status == "KEEP":
        return _GREEN
    if status == "REVIEW":
        return _YELLOW
    return _RED  # DROP_* and any unknown status


def write_xlsx(rows: List[dict], input_columns: List[str], out_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Catalog Audit"

    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = list(input_columns) + AUDIT_COLS
    ws.append(headers)
    for ci, _ in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci)
        c.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", start_color="1DB954")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    ws.row_dimensions[1].height = 28

    for ri, row in enumerate(rows, 2):
        status = row.get("Status", "REVIEW")
        fill = _row_fill(status)
        for ci, h in enumerate(headers, 1):
            val = row.get(h, "")
            if isinstance(val, list):
                val = " | ".join(str(x) for x in val if x)
            c = ws.cell(row=ri, column=ci, value=val)
            c.font = Font(name="Arial", size=9)
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = border
            c.fill = fill

    widths = {
        "Artist": 24,
        "Status": 14,
        "Status Reason": 50,
        "Label Evaluations": 70,
        "Verdict": 11,
        "Earliest Year": 12,
        "Earliest Year Note": 28,
        "iTunes P-Line": 50,
        "iTunes Licensee": 22,
        "Deezer Labels": 28,
        "Discogs Labels": 28,
        "Informational Notes": 50,
        "Flag Reasons": 60,
        "Associated Labels": 22,
        "Spotify Links": 36,
    }
    for ci, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(ci)].width = widths.get(h, 16)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))


# ---------------------------------------------------------------------------
# Filter / export helper
# ---------------------------------------------------------------------------

# Map UI filter kinds to the set of Status values they include.
_FILTER_STATUSES = {
    "keep":   {"KEEP"},
    "review": {"REVIEW"},
    "drop":   {"DROP_MAJOR", "DROP_LICENSED", "DROP_THIRDPARTY"},
    "all":    {"KEEP", "REVIEW", "DROP_MAJOR", "DROP_LICENSED", "DROP_THIRDPARTY"},
}


def filter_xlsx_by_status(
    src_path: Path,
    filter_kind: str,
) -> Tuple[Optional[Path], int]:
    """
    Read an existing audit xlsx, copy only rows whose Status column matches
    the filter, and write the filtered result to a fresh tempfile.

    Returns (filtered_path, kept_count). If no rows matched the filter,
    returns (None, 0) so the caller can return a useful 404 to the user.

    The returned path lives in the system tempdir; callers should treat it
    as a one-shot download artifact (Flask streams it then it can be
    cleaned up by the OS).
    """
    filter_kind = (filter_kind or "keep").strip().lower()
    keep_statuses = _FILTER_STATUSES.get(filter_kind)
    if keep_statuses is None:
        raise ValueError(f"unknown filter '{filter_kind}'")

    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(str(src))

    src_wb = load_workbook(str(src))
    src_ws = src_wb.active

    # Find the Status column index (1-based).
    headers = [c.value for c in src_ws[1]]
    try:
        status_col = headers.index("Status") + 1
    except ValueError:
        raise RuntimeError("source xlsx has no 'Status' column")

    out_wb = Workbook()
    out_ws = out_wb.active
    out_ws.title = src_ws.title

    # Copy the header row, preserving widths and styling.
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    out_ws.append(headers)
    for ci, _ in enumerate(headers, 1):
        c = out_ws.cell(row=1, column=ci)
        c.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", start_color="1DB954")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    out_ws.row_dimensions[1].height = 28

    # Copy column widths.
    for col_letter, dim in src_ws.column_dimensions.items():
        if dim.width:
            out_ws.column_dimensions[col_letter].width = dim.width

    # Copy filtered rows.
    kept = 0
    for src_row in src_ws.iter_rows(min_row=2, values_only=False):
        status_cell = src_row[status_col - 1]
        status_val = (status_cell.value or "").strip() if isinstance(status_cell.value, str) else status_cell.value
        if status_val not in keep_statuses:
            continue
        kept += 1
        out_row_idx = kept + 1  # accounting for header
        for ci, src_cell in enumerate(src_row, 1):
            out_cell = out_ws.cell(row=out_row_idx, column=ci, value=src_cell.value)
            out_cell.font = Font(name="Arial", size=9)
            out_cell.alignment = Alignment(vertical="center", wrap_text=True)
            out_cell.border = border
            out_cell.fill = _row_fill(status_val if isinstance(status_val, str) else "")

    if kept == 0:
        return (None, 0)

    out_ws.freeze_panes = "A2"
    out_ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    # Write to a tempfile; Flask will stream it.
    tmp_dir = Path(tempfile.gettempdir())
    out_path = tmp_dir / f"{src.stem}-{filter_kind}.xlsx"
    out_wb.save(str(out_path))
    return (out_path, kept)
