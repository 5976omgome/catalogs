"""Per-job runner. One worker thread per process processes the queue
sequentially. Stop semantics: cooperative cancel mid-run; current artist
finishes; partial xlsx is written.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from . import audit as audit_mod
from . import config, excel

# ---- column aliases for tolerant CSV header matching ----
_HEADER_ALIASES = {
    "Artist": ("artist", "artist name", "performer", "name"),
    "Associated Labels": ("associated labels", "label", "associatedlabel",
                          "current label"),
    "Spotify Links": ("spotify links", "spotify url", "spotify", "spotify link"),
    "Genres": ("genres", "genre"),
    "Region": ("region", "country", "territory"),
    "Spotify Monthly Listeners": ("spotify monthly listeners", "monthly listeners"),
    "Recent Momentum": ("recent momentum", "momentum"),
    "First Release Date": ("first release date", "earliest release",
                           "first release", "first release year"),
    "Latest Release Date": ("latest release date", "most recent release"),
}


def _normalise_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Renames CSV columns to canonical names. Case-insensitive match."""
    lower_map = {c.lower().strip(): c for c in df.columns}
    rename: Dict[str, str] = {}
    for canonical, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            if alias in lower_map and canonical != lower_map[alias]:
                rename[lower_map[alias]] = canonical
                break
    if rename:
        df = df.rename(columns=rename)
    return df


_DATE_FORMATS = ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y")


def _parse_year(value: Any) -> Optional[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit() and 1900 <= int(s) <= 2100:
        return int(s)
    for fmt in _DATE_FORMATS:
        try:
            return pd.to_datetime(s, format=fmt).year
        except Exception:
            continue
    try:
        return pd.to_datetime(s, errors="coerce").year
    except Exception:
        return None


# --------------------------------------------------------------------------
# JobItem & JobManager
# --------------------------------------------------------------------------

@dataclass
class JobItem:
    id: str
    filename: str
    path: Path
    output_path: Optional[Path] = None
    status: str = "queued"      # queued | running | done | stopped | error
    total: int = 0
    processed: int = 0
    keep: int = 0
    review: int = 0
    drop: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "filename": self.filename, "status": self.status,
            "total": self.total, "processed": self.processed,
            "keep": self.keep, "review": self.review, "drop": self.drop,
            "error": self.error,
            "has_output": bool(self.output_path and self.output_path.exists()),
        }


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: List[JobItem] = []
        self._subscribers: List["queue.Queue[Dict[str, Any]]"] = []
        self._sub_lock = threading.Lock()
        self._worker: Optional[threading.Thread] = None
        self._running = False
        self._stop_requested = False

    # ------------------------------------------------------------------
    # Subscribers (SSE)
    # ------------------------------------------------------------------
    def subscribe(self) -> "queue.Queue[Dict[str, Any]]":
        q: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=512)
        with self._sub_lock:
            self._subscribers.append(q)
        # Send a snapshot so a freshly-connected client sees current state.
        q.put_nowait({"type": "snapshot", "items": self.snapshot()})
        return q

    def unsubscribe(self, q: "queue.Queue[Dict[str, Any]]") -> None:
        with self._sub_lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def _broadcast(self, event: Dict[str, Any]) -> None:
        with self._sub_lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------
    def add(self, filename: str, path: Path) -> JobItem:
        item = JobItem(id=uuid.uuid4().hex[:12], filename=filename, path=path)
        with self._lock:
            self._items.append(item)
        self._broadcast({"type": "item_added", "item": item.to_dict()})
        return item

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [it.to_dict() for it in self._items]

    def find(self, item_id: str) -> Optional[JobItem]:
        with self._lock:
            for it in self._items:
                if it.id == item_id:
                    return it
        return None

    def clear(self) -> None:
        with self._lock:
            # only remove finished/stopped items; running stays
            self._items = [it for it in self._items
                           if it.status in ("running",)]
        self._broadcast({"type": "cleared"})

    # ------------------------------------------------------------------
    # Run / stop
    # ------------------------------------------------------------------
    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._stop_requested = False
        t = threading.Thread(target=self._run_loop, daemon=True)
        self._worker = t
        t.start()
        return True

    def stop(self) -> bool:
        with self._lock:
            if not self._running:
                return False
            self._stop_requested = True
        return True

    @property
    def is_running(self) -> bool:
        return self._running

    def _run_loop(self) -> None:
        try:
            while True:
                if self._stop_requested:
                    break
                with self._lock:
                    nxt = next((it for it in self._items if it.status == "queued"), None)
                if nxt is None:
                    break
                self._run_item(nxt)
        finally:
            with self._lock:
                self._running = False
                self._stop_requested = False
            self._broadcast({"type": "queue_done"})

    # ------------------------------------------------------------------
    # Per-item processing
    # ------------------------------------------------------------------
    def _run_item(self, item: JobItem) -> None:
        with self._lock:
            item.status = "running"
        self._broadcast({"type": "item_started", "item": item.to_dict()})

        try:
            df = pd.read_csv(item.path)
            df = _normalise_headers(df)
        except Exception as e:
            with self._lock:
                item.status = "error"
                item.error = f"CSV read failed: {e}"
            self._broadcast({"type": "item_error", "item": item.to_dict()})
            self._cleanup_upload(item.path)
            return

        if "Artist" not in df.columns:
            with self._lock:
                item.status = "error"
                item.error = "CSV missing 'Artist' column"
            self._broadcast({"type": "item_error", "item": item.to_dict()})
            self._cleanup_upload(item.path)
            return

        with self._lock:
            item.total = len(df)

        # Sanitize Spotify Links: keep first URL if comma-separated
        if "Spotify Links" in df.columns:
            df["Spotify Links"] = df["Spotify Links"].apply(
                lambda v: (str(v).split(",")[0].strip()
                           if isinstance(v, str) and v.strip() else "")
            )

        # Output columns we'll fill in
        new_cols = [
            "Status", "Status Reason", "iTunes P-Line", "Licensee",
            "Earliest Year", "Earliest Year Note",
            "Label Evaluations", "AI / Informational", "Verdict",
        ]
        for c in new_cols:
            if c not in df.columns:
                df[c] = ""

        # Per-artist loop
        cancelled = False
        for idx, row in df.iterrows():
            if self._stop_requested:
                cancelled = True
                break

            artist = str(row.get("Artist", "")).strip()
            cm_label = str(row.get("Associated Labels", "")).strip() if "Associated Labels" in df.columns else ""
            cm_year = _parse_year(row.get("First Release Date")) if "First Release Date" in df.columns else None

            try:
                a = audit_mod.audit_artist(
                    artist=artist,
                    chartmetric_label=cm_label,
                    chartmetric_first_year=cm_year,
                )
            except Exception as e:
                a = audit_mod.ArtistAudit(artist=artist)
                a.status = "REVIEW"
                a.status_reason = f"Audit error: {e}"

            # Compose the iTunes P-line text by joining the raw copyright
            # strings of the first few releases with " | "
            try:
                from .sources import itunes as itunes_mod
                pline_releases = itunes_mod.get_releases(artist, limit=3)
                pline_text = " | ".join(
                    r.get("copyright", "").strip() for r in pline_releases
                    if r.get("copyright")
                )
            except Exception:
                pline_text = ""

            evals_text = " | ".join(
                f"{e.source}={e.label}[{e.classification}]"
                for e in a.evaluations
            )

            df.at[idx, "Status"] = a.status
            df.at[idx, "Status Reason"] = a.status_reason
            df.at[idx, "iTunes P-Line"] = pline_text
            df.at[idx, "Licensee"] = a.licensee or ""
            df.at[idx, "Earliest Year"] = a.earliest_year or ""
            df.at[idx, "Earliest Year Note"] = a.earliest_year_note
            df.at[idx, "Label Evaluations"] = evals_text
            df.at[idx, "AI / Informational"] = " | ".join(a.informational)
            df.at[idx, "Verdict"] = a.verdict

            with self._lock:
                item.processed += 1
                if a.status == "KEEP":
                    item.keep += 1
                elif a.status == "REVIEW":
                    item.review += 1
                else:
                    item.drop += 1

            self._broadcast({
                "type": "artist_done",
                "item_id": item.id,
                "artist": artist,
                "status": a.status,
                "status_reason": a.status_reason,
                "evaluations": evals_text,
                "processed": item.processed,
                "total": item.total,
                "keep": item.keep, "review": item.review, "drop": item.drop,
            })

        # Write the xlsx (full or partial). We always write something so
        # the user can export even after a stop.
        out_dir = config.OUTPUT_DIR
        stem = Path(item.filename).stem
        suffix = "PartialOutput" if cancelled else "Output"
        # Trim only the rows we actually processed
        processed_df = df.iloc[: item.processed].copy() if cancelled else df
        out_path = out_dir / f"{stem}{suffix}.xlsx"
        try:
            excel.write_xlsx(processed_df, out_path)
            with self._lock:
                item.output_path = out_path
        except Exception as e:
            with self._lock:
                item.status = "error"
                item.error = f"xlsx write failed: {e}"
            self._broadcast({"type": "item_error", "item": item.to_dict()})
            self._cleanup_upload(item.path)
            return

        with self._lock:
            item.status = "stopped" if cancelled else "done"
        self._broadcast({
            "type": "item_stopped" if cancelled else "item_done",
            "item": item.to_dict(),
        })
        self._cleanup_upload(item.path)

    def _cleanup_upload(self, path: Path) -> None:
        try:
            if path.exists() and path.parent == config.UPLOAD_DIR:
                path.unlink()
        except Exception:
            pass


_manager_singleton: Optional[JobManager] = None
_manager_lock = threading.Lock()


def get_manager() -> JobManager:
    global _manager_singleton
    with _manager_lock:
        if _manager_singleton is None:
            _manager_singleton = JobManager()
        return _manager_singleton
