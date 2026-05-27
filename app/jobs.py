"""Background job manager with SSE event broadcasting."""
import json
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .audit import audit_artist
from .config import OUTPUT_DIR
from .excel import write_xlsx

# CSV header aliases - map common variants to canonical names
HEADER_ALIASES = {
    "artist": "Artist",
    "artist name": "Artist",
    "performer": "Artist",
    "associated labels": "Associated Labels",
    "label": "Associated Labels",
    "labels": "Associated Labels",
    "first release date": "First Release Date",
    "first release": "First Release Date",
    "debut date": "First Release Date",
    "spotify links": "Spotify Links",
    "spotify link": "Spotify Links",
    "spotify url": "Spotify Links",
}


@dataclass
class JobItem:
    item_id: str
    filename: str
    path: str
    total: int = 0
    processed: int = 0
    clean: int = 0
    flagged: int = 0
    status: str = "queued"  # queued | running | done | error
    output_path: str = ""
    error: str = ""


@dataclass
class _Subscriber:
    q: "queue.Queue[str]" = field(default_factory=lambda: queue.Queue(maxsize=1000))


class JobManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._items: Dict[str, JobItem] = {}
        self._order: List[str] = []
        self._subs: List[_Subscriber] = []
        self._worker: Optional[threading.Thread] = None
        self._running = False

    # --- subscriber API for SSE ---
    def subscribe(self) -> _Subscriber:
        sub = _Subscriber()
        with self._lock:
            self._subs.append(sub)
        # Send a snapshot immediately
        self._send_to(sub, {"type": "snapshot", "items": self._snapshot()})
        return sub

    def unsubscribe(self, sub: _Subscriber):
        with self._lock:
            try:
                self._subs.remove(sub)
            except ValueError:
                pass

    def _broadcast(self, payload: dict):
        msg = json.dumps(payload)
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            try:
                sub.q.put_nowait(msg)
            except queue.Full:
                pass

    def _send_to(self, sub: _Subscriber, payload: dict):
        try:
            sub.q.put_nowait(json.dumps(payload))
        except queue.Full:
            pass

    # --- queue API ---
    def add(self, filename: str, path: str) -> JobItem:
        item = JobItem(item_id=str(uuid.uuid4()), filename=filename, path=path)
        with self._lock:
            self._items[item.item_id] = item
            self._order.append(item.item_id)
        self._broadcast({"type": "item_added", "item": self._item_dict(item)})
        return item

    def remove(self, item_id: str):
        with self._lock:
            if item_id in self._items:
                del self._items[item_id]
                self._order = [i for i in self._order if i != item_id]
        self._broadcast({"type": "item_removed", "item_id": item_id})

    def clear(self):
        with self._lock:
            self._items.clear()
            self._order.clear()
        self._broadcast({"type": "queue_cleared"})

    def _snapshot(self) -> List[dict]:
        with self._lock:
            return [self._item_dict(self._items[i]) for i in self._order if i in self._items]

    def _item_dict(self, item: JobItem) -> dict:
        return {
            "item_id": item.item_id,
            "filename": item.filename,
            "total": item.total,
            "processed": item.processed,
            "clean": item.clean,
            "flagged": item.flagged,
            "status": item.status,
            "output_path": item.output_path,
            "error": item.error,
        }

    # --- run ---
    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._worker = threading.Thread(target=self._run_loop, daemon=True)
            self._worker.start()
        self._broadcast({"type": "queue_started"})

    def _run_loop(self):
        try:
            while True:
                with self._lock:
                    next_id = None
                    for iid in self._order:
                        it = self._items.get(iid)
                        if it and it.status == "queued":
                            next_id = iid
                            break
                if not next_id:
                    break
                self._run_item(next_id)
        finally:
            with self._lock:
                self._running = False
            self._broadcast({"type": "queue_done"})

    def _run_item(self, item_id: str):
        with self._lock:
            item = self._items.get(item_id)
        if not item:
            return

        item.status = "running"
        self._broadcast({"type": "item_status", "item_id": item.item_id,
                         "status": "running"})

        try:
            df = pd.read_csv(item.path)
            df = _normalize_headers(df)

            if "Artist" not in df.columns:
                raise RuntimeError("CSV missing 'Artist' column")

            # Trim multi-spotify-links cells to first
            if "Spotify Links" in df.columns:
                df["Spotify Links"] = df["Spotify Links"].apply(_first_link)

            input_columns = list(df.columns)
            total = len(df)
            item.total = total
            self._broadcast({"type": "item_total", "item_id": item.item_id,
                             "total": total})

            output_rows = []
            for i, row in df.iterrows():
                artist = str(row.get("Artist", "")).strip()
                cm_label = str(row.get("Associated Labels", "")).strip() if "Associated Labels" in df.columns else ""
                cm_first = ""
                if "First Release Date" in df.columns:
                    cm_first = _parse_year(str(row.get("First Release Date", "")))

                self._broadcast({
                    "type": "artist_start",
                    "item_id": item.item_id,
                    "index": int(i) + 1,
                    "artist": artist,
                })

                audit = audit_artist(artist, cm_label, cm_first)

                out_row = {col: row.get(col, "") for col in input_columns}
                out_row["Verdict"] = audit.verdict
                out_row["Earliest Year"] = audit.earliest_year
                out_row["iTunes P-Line"] = audit.itunes_pline
                out_row["iTunes Licensee"] = audit.itunes_licensee
                out_row["Deezer Labels"] = audit.deezer_labels
                out_row["Discogs Labels"] = audit.discogs_labels
                out_row["Likely Self-Imprint"] = "yes" if audit.likely_self_imprint else ""
                out_row["Flag Reasons"] = audit.flag_reasons
                output_rows.append(out_row)

                item.processed = int(i) + 1
                if audit.verdict == "CLEAN":
                    item.clean += 1
                else:
                    item.flagged += 1

                self._broadcast({
                    "type": "artist_done",
                    "item_id": item.item_id,
                    "index": int(i) + 1,
                    "artist": artist,
                    "verdict": audit.verdict,
                    "pline": audit.itunes_pline,
                    "earliest_year": audit.earliest_year,
                    "self_imprint": audit.likely_self_imprint,
                    "flag_reasons": audit.flag_reasons,
                    "processed": item.processed,
                    "total": item.total,
                    "clean": item.clean,
                    "flagged": item.flagged,
                })

            stem = Path(item.filename).stem
            out_path = OUTPUT_DIR / f"{stem}Output.xlsx"
            write_xlsx(output_rows, input_columns, out_path)
            item.output_path = str(out_path)
            item.status = "done"
            self._broadcast({
                "type": "item_done",
                "item_id": item.item_id,
                "output_path": item.output_path,
                "clean": item.clean,
                "flagged": item.flagged,
                "total": item.total,
            })

        except Exception as e:
            item.status = "error"
            item.error = str(e)
            self._broadcast({
                "type": "item_error",
                "item_id": item.item_id,
                "error": item.error,
            })


# --- helpers ---

def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Map common header variants to canonical names."""
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in HEADER_ALIASES:
            rename[col] = HEADER_ALIASES[key]
    if rename:
        df = df.rename(columns=rename)
    return df


def _first_link(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v)
    return s.split(",")[0].strip()


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_year(s: str) -> str:
    """Parse a year out of common date formats. 'Oct 30, 2019' -> '2019'."""
    if not s or s.lower() in ("nan", "none", ""):
        return ""
    s = s.strip()
    m = re.search(r"(19|20)\d{2}", s)
    return m.group(0) if m else ""


# Singleton
manager = JobManager()
