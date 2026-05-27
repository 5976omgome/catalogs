"""Excel output writer.

Three-color row palette driven by the new Status column:
    KEEP            -> green   (worth pursuing)
    REVIEW          -> yellow  (mixed signals - human eyes needed)
    DROP_*          -> red     (any DROP_MAJOR / DROP_LICENSED / DROP_THIRDPARTY)

Legacy Verdict column (CLEAN/FLAGGED) is retained for backwards compat
with any consumer that filters on it.
"""
from pathlib import Path
from typing import List

from openpyxl import Workbook
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
