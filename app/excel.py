"""Excel writer for audit results."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUTPUT_COLS = [
    "Artist",
    "Spotify Links",
    "Genres",
    "Region",
    "Spotify Monthly Listeners",
    "Associated Labels",
    "Recent Momentum",
    "Deezer Labels Found",
    "Discogs Labels Found",
    "Ever Signed",
    "Flag",
    "AI Verdict",
    "AI Reason",
]

COL_WIDTHS = {
    "Artist": 22,
    "Spotify Links": 44,
    "Genres": 26,
    "Region": 14,
    "Spotify Monthly Listeners": 14,
    "Associated Labels": 22,
    "Recent Momentum": 13,
    "Deezer Labels Found": 32,
    "Discogs Labels Found": 32,
    "Ever Signed": 11,
    "Flag": 46,
    "AI Verdict": 12,
    "AI Reason": 52,
}


def write(df: pd.DataFrame, path: Path | str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Catalog Audit"

    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    headers = [c for c in OUTPUT_COLS if c in df.columns]
    ws.append(headers)
    for ci, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci)
        cell.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
        cell.fill = PatternFill("solid", start_color="1DB954")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[1].height = 28

    spotify_col = headers.index("Spotify Links") + 1 if "Spotify Links" in headers else None
    verdict_col = headers.index("AI Verdict") + 1 if "AI Verdict" in headers else None
    reason_col = headers.index("AI Reason") + 1 if "AI Reason" in headers else None

    for ri, row in enumerate(df[headers].itertuples(index=False), 2):
        verdict = (str(row[verdict_col - 1]) if verdict_col else "").upper()
        if verdict == "FLAGGED":
            row_fill = PatternFill("solid", start_color="FFD7D7")
        elif verdict == "CAUTION":
            row_fill = PatternFill("solid", start_color="FFF3CD")
        elif verdict == "CLEAN":
            row_fill = PatternFill("solid", start_color="E6F7E9")
        elif ri % 2 == 0:
            row_fill = PatternFill("solid", start_color="F7F7F7")
        else:
            row_fill = None

        for ci, value in enumerate(row, 1):
            cell = ws.cell(row=ri, column=ci, value=value)
            cell.font = Font(name="Arial", size=9)
            cell.border = border
            wrap = ci in {reason_col, headers.index("Flag") + 1 if "Flag" in headers else -1}
            cell.alignment = Alignment(vertical="center", wrap_text=wrap)
            if row_fill:
                cell.fill = row_fill

        if spotify_col:
            link = df["Spotify Links"].iloc[ri - 2]
            if pd.notna(link) and str(link).startswith("http"):
                lc = ws.cell(row=ri, column=spotify_col)
                lc.hyperlink = link
                lc.value = link
                lc.font = Font(name="Arial", size=9, color="1155CC", underline="single")

    for ci, name in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(ci)].width = COL_WIDTHS.get(name, 16)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    wb.save(path)
