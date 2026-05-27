"""Excel output writer."""
from pathlib import Path
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

AUDIT_COLS = [
    "Verdict", "Earliest Year", "iTunes P-Line", "iTunes Licensee",
    "Deezer Labels", "Discogs Labels", "Likely Self-Imprint", "Flag Reasons",
]


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

    green_fill = PatternFill("solid", start_color="E6F4EA")
    red_fill = PatternFill("solid", start_color="FCE4E4")

    for ri, row in enumerate(rows, 2):
        verdict = row.get("Verdict", "FLAGGED")
        for ci, h in enumerate(headers, 1):
            val = row.get(h, "")
            if isinstance(val, list):
                val = " | ".join(str(x) for x in val if x)
            c = ws.cell(row=ri, column=ci, value=val)
            c.font = Font(name="Arial", size=9)
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = border
            if verdict == "CLEAN":
                c.fill = green_fill
            else:
                c.fill = red_fill

    widths = {
        "Artist": 24, "Verdict": 11, "Earliest Year": 12,
        "iTunes P-Line": 50, "iTunes Licensee": 22,
        "Deezer Labels": 28, "Discogs Labels": 28,
        "Likely Self-Imprint": 14, "Flag Reasons": 60,
        "Associated Labels": 22, "Spotify Links": 36,
    }
    for ci, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(ci)].width = widths.get(h, 16)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
