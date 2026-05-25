"""Excel writer for audit results."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .labels import OLD_CATALOG_CUTOFF

# Audit columns appended to every output, in display order.
AUDIT_COLS = [
    "Apple P-Line",
    "Apple Owners",
    "Apple Licensed-To",
    "Deezer Labels Found",
    "Discogs Labels Found",
    "First Release Year",
    "Ever Signed",
    "Has Licensing",
    "Likely Self-Imprint",
    "Flag",
    "AI Verdict",
    "AI Reason",
]

# Width hints
COL_WIDTHS = {
    "Artist": 22,
    "Spotify Links": 44,
    "Genres": 26,
    "Region": 14,
    "Spotify Monthly Listeners": 14,
    "Associated Labels": 22,
    "Recent Momentum": 13,
    "Apple P-Line": 60,
    "Apple Owners": 30,
    "Apple Licensed-To": 28,
    "Deezer Labels Found": 28,
    "Discogs Labels Found": 28,
    "First Release Year": 11,
    "Ever Signed": 11,
    "Has Licensing": 12,
    "Likely Self-Imprint": 13,
    "Flag": 50,
    "AI Verdict": 11,
    "AI Reason": 60,
}

WRAP_COLS = {"Apple P-Line", "Flag", "AI Reason"}

CLEAN_FILL = PatternFill("solid", start_color="D8F3DC")
FLAG_FILL = PatternFill("solid", start_color="FFD7D7")
ALT_FILL = PatternFill("solid", start_color="F7F7F7")
OLD_YEAR_FILL = PatternFill("solid", start_color="FFC1A6")


def write(df: pd.DataFrame, path: Path | str, *, clean_only: bool = False) -> None:
    """Write the audit dataframe to an .xlsx file.

    If clean_only=True, filter to verdict CLEAN before writing. The
    full sheet always preserves every input row; clean_only is a
    convenience export for quick scanning.
    """
    if clean_only and "AI Verdict" in df.columns:
        df = df[df["AI Verdict"].astype(str).str.upper() == "CLEAN"].copy()

    wb = Workbook()
    ws = wb.active
    ws.title = "Catalog Audit"

    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Preserve any input columns the user already had, then append our
    # audit columns at the end. This guarantees we never drop information
    # from the source CSV.
    user_cols = [c for c in df.columns if c not in AUDIT_COLS]
    audit_cols_present = [c for c in AUDIT_COLS if c in df.columns]
    headers = user_cols + audit_cols_present
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
    year_col = headers.index("First Release Year") + 1 if "First Release Year" in headers else None

    for ri, row in enumerate(df[headers].itertuples(index=False), 2):
        verdict = (str(row[verdict_col - 1]) if verdict_col else "").upper()
        if verdict == "CLEAN":
            row_fill = CLEAN_FILL
        elif verdict == "FLAGGED":
            row_fill = FLAG_FILL
        else:
            row_fill = ALT_FILL if ri % 2 == 0 else None

        for ci, value in enumerate(row, 1):
            cell = ws.cell(row=ri, column=ci, value=value)
            cell.font = Font(name="Arial", size=9)
            cell.border = border
            wrap = headers[ci - 1] in WRAP_COLS
            cell.alignment = Alignment(vertical="center", wrap_text=wrap)
            if row_fill:
                cell.fill = row_fill

        # Year heat-shade (overrides row fill for that one cell)
        if year_col:
            yval = row[year_col - 1]
            try:
                y = int(str(yval)) if str(yval).strip() else 0
            except ValueError:
                y = 0
            if y and y < OLD_CATALOG_CUTOFF:
                ws.cell(row=ri, column=year_col).fill = OLD_YEAR_FILL

        # Hyperlink Spotify column
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
    if headers:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    wb.save(path)
