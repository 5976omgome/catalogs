"""Background job manager with SSE event broadcasting.

All mutations to JobItem fields go through methods that hold the manager
lock, so concurrent readers (snapshot, broadcast payload builders) see
consistent state.

Uploaded source CSVs are removed from .uploads/ once a job finishes
(success or error) so the directory never accumulates forever.
"""
import contextlib
import json
import queue
import re
import threading
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
    # Legacy counters - kept so existing UI fields don't change shape.
    clean: int = 0
    flagged: int = 0
    # New richer counters
    keep: int = 0
    review: int = 0
    drop: int = 0
    status: str = "queued"  # queued | running | done | error
    output_path: str = ""
    error: str = ""
    # Mid-run export support: we keep the partial output rows + the input
    # column order in memory so /api/export_partial/<item_id> can build a
    # fresh xlsx WHILE the run is still in progress. These are populated
    # after each artist completes, under the manager lock.
    partial_rows: List[dict] = field(default_factory=list)
    input_columns: List[str] = field(default_factory=list)


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
        self._stop_requested = False

    # --- subscriber API for SSE ---
    def subscribe(self) -> _Subscriber:
        sub = _Subscriber()
        with self._lock:
            self._subs.append(sub)
        # Send a snapshot immediately so a fresh client paints the queue.
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
            payload = self._item_dict(item)
        self._broadcast({"type": "item_added", "item": payload})
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
            return [
                self._item_dict(self._items[i])
                for i in self._order
                if i in self._items
            ]

    # Public alias - thread-safe, used by HTTP handlers.
    def snapshot(self) -> List[dict]:
        return self._snapshot()

    def get_partial(self, item_id: str) -> Optional[dict]:
        """
        Return a thread-safe snapshot of an item's in-memory rows-so-far,
        for the mid-run export endpoint. Returns None if the item is gone
        or has no rows yet.
        """
        with self._lock:
            it = self._items.get(item_id)
            if it is None:
                return None
            if not it.partial_rows:
                return None
            return {
                "filename": it.filename,
                "status": it.status,
                "processed": it.processed,
                "total": it.total,
                # Shallow copy of the row list is enough - row dicts are
                # written once per artist and never mutated.
                "rows": list(it.partial_rows),
                "input_columns": list(it.input_columns),
            }

    def _item_dict(self, item: JobItem) -> dict:
        # Caller must hold self._lock when item is owned by the manager.
        return {
            "item_id": item.item_id,
            "filename": item.filename,
            "total": item.total,
            "processed": item.processed,
            "clean": item.clean,
            "flagged": item.flagged,
            "keep": item.keep,
            "review": item.review,
            "drop": item.drop,
            "status": item.status,
            "output_path": item.output_path,
            "error": item.error,
        }

    def _update_item(self, item_id: str, **fields) -> Optional[dict]:
        """
        Atomically apply field updates to a JobItem and return its snapshot.
        Returns None if the item has been removed from the queue.
        """
        with self._lock:
            it = self._items.get(item_id)
            if not it:
                return None
            for k, v in fields.items():
                setattr(it, k, v)
            return self._item_dict(it)

    def _bump_counters(
        self,
        item_id: str,
        processed: int,
        clean_inc: int,
        flagged_inc: int,
        keep_inc: int = 0,
        review_inc: int = 0,
        drop_inc: int = 0,
    ) -> Optional[dict]:
        """Atomic counter bump for one artist completing."""
        with self._lock:
            it = self._items.get(item_id)
            if not it:
                return None
            it.processed = processed
            it.clean += clean_inc
            it.flagged += flagged_inc
            it.keep += keep_inc
            it.review += review_inc
            it.drop += drop_inc
            return self._item_dict(it)

    # --- run ---
    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_requested = False
            self._worker = threading.Thread(target=self._run_loop, daemon=True)
            self._worker.start()
        self._broadcast({"type": "queue_started"})

    def stop(self):
        """
        Request a graceful stop. The currently-running item finishes the
        artist it's on, writes its partial xlsx output (with whatever rows
        were processed), and is marked 'stopped'. Remaining queued items
        stay in the queue but won't be processed until start() is called
        again.
        """
        with self._lock:
            if not self._running:
                return
            self._stop_requested = True
        self._broadcast({"type": "queue_stop_requested"})

    def _run_loop(self):
        try:
            while True:
                with self._lock:
                    if self._stop_requested:
                        break
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
                self._stop_requested = False
            self._broadcast({"type": "queue_done"})

    def _run_item(self, item_id: str):
        # Snapshot the path/filename inside the lock so we don't race with
        # remove() / clear() while reading them.
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return
            src_path = item.path
            filename = item.filename

        snap = self._update_item(item_id, status="running")
        if snap is None:  # cleared mid-flight
            self._cleanup_upload(src_path)
            return
        self._broadcast({"type": "item_status", "item_id": item_id,
                         "status": "running"})

        try:
            df = pd.read_csv(src_path)
            df = _normalize_headers(df)

            if "Artist" not in df.columns:
                raise RuntimeError("CSV missing 'Artist' column")

            if "Spotify Links" in df.columns:
                df["Spotify Links"] = df["Spotify Links"].apply(_first_link)

            input_columns = list(df.columns)
            total = len(df)
            self._update_item(item_id, total=total)
            self._broadcast({"type": "item_total", "item_id": item_id,
                             "total": total})

            output_rows = []
            stopped_mid_run = False
            for i, row in df.iterrows():
                # Cooperative cancel: if the user cleared the queue mid-run,
                # stop processing this file.
                with self._lock:
                    if item_id not in self._items:
                        break
                    if self._stop_requested:
                        stopped_mid_run = True
                        break

                artist = str(row.get("Artist", "")).strip()
                cm_label = (
                    str(row.get("Associated Labels", "")).strip()
                    if "Associated Labels" in df.columns else ""
                )
                cm_first = ""
                if "First Release Date" in df.columns:
                    cm_first = _parse_year(str(row.get("First Release Date", "")))

                self._broadcast({
                    "type": "artist_start",
                    "item_id": item_id,
                    "index": int(i) + 1,
                    "artist": artist,
                })

                audit = audit_artist(artist, cm_label, cm_first)

                # Format per-label evaluations into a single human string for
                # the Excel sheet AND for the SSE payload.
                eval_strs = [
                    f"[{ev.source}] {ev.label!r}: {ev.status} ({ev.reason})"
                    for ev in audit.label_evaluations
                ]

                # Per-source roll-up for the live log: one line per source
                # (Chartmetric / iTunes / Deezer / Discogs) with that
                # source's worst hit. Priority: MAJOR > LICENSED >
                # THIRDPARTY > VARIANT > DISTRIBUTOR.
                per_source = _summarize_per_source(audit.label_evaluations)

                # Earliest-year informational note ("OLD_CATALOG: ...") is
                # kept separate from the row's flag reasons under the new
                # spec - old catalog is desirable for catalogue deals.
                old_catalog_note = next(
                    (n for n in audit.informational if n.startswith("OLD_CATALOG")),
                    "",
                )

                out_row = {col: row.get(col, "") for col in input_columns}
                out_row["Status"] = audit.status
                out_row["Status Reason"] = audit.status_reason
                out_row["Label Evaluations"] = eval_strs
                out_row["Verdict"] = audit.verdict
                out_row["Earliest Year"] = audit.earliest_year
                out_row["Earliest Year Note"] = old_catalog_note
                out_row["iTunes P-Line"] = audit.itunes_pline
                out_row["iTunes Licensee"] = audit.itunes_licensee
                out_row["Deezer Labels"] = audit.deezer_labels
                out_row["Discogs Labels"] = audit.discogs_labels
                out_row["Informational Notes"] = audit.informational
                out_row["Flag Reasons"] = audit.flag_reasons
                output_rows.append(out_row)

                # Also stash on the JobItem so a mid-run export can read
                # the rows-so-far. Copy by value (the dict is freshly built
                # per artist, so output_rows can keep its own reference).
                with self._lock:
                    it = self._items.get(item_id)
                    if it is not None:
                        it.partial_rows = list(output_rows)
                        it.input_columns = list(input_columns)

                # Bucket counters: KEEP/REVIEW/DROP plus legacy CLEAN/FLAGGED.
                is_keep = audit.status == "KEEP"
                is_review = audit.status == "REVIEW"
                is_drop = audit.status.startswith("DROP_")
                snap = self._bump_counters(
                    item_id,
                    processed=int(i) + 1,
                    clean_inc=1 if is_keep else 0,
                    flagged_inc=0 if is_keep else 1,
                    keep_inc=1 if is_keep else 0,
                    review_inc=1 if is_review else 0,
                    drop_inc=1 if is_drop else 0,
                )
                if snap is None:  # cleared mid-flight
                    break

                # Deduplicate flag reasons so a single label hit doesn't
                # appear once per (owner, P-line) pair. We keep the first
                # occurrence per (source-family, status, label) tuple.
                seen_flags = set()
                deduped_flag_reasons = []
                for fr in audit.flag_reasons:
                    # Normalize "iTunes (P-line):" / "iTunes (licensee):" /
                    # "iTunes:" to a single bucket per outcome+label.
                    fr_key = re.sub(r"^iTunes \([^)]+\):", "iTunes:", fr)
                    if fr_key in seen_flags:
                        continue
                    seen_flags.add(fr_key)
                    deduped_flag_reasons.append(fr)

                self._broadcast({
                    "type": "artist_done",
                    "item_id": item_id,
                    "index": int(i) + 1,
                    "artist": artist,
                    "status": audit.status,
                    "status_reason": audit.status_reason,
                    "label_evaluations": eval_strs,
                    "per_source": per_source,
                    "informational": audit.informational,
                    # Legacy fields kept for the existing front-end:
                    "verdict": audit.verdict,
                    "pline": audit.itunes_pline,
                    "earliest_year": audit.earliest_year,
                    "self_imprint": audit.likely_self_imprint,
                    "flag_reasons": deduped_flag_reasons,
                    "processed": snap["processed"],
                    "total": snap["total"],
                    "clean": snap["clean"],
                    "flagged": snap["flagged"],
                    "keep": snap["keep"],
                    "review": snap["review"],
                    "drop": snap["drop"],
                })

            # If the item was removed during the loop, don't write output.
            with self._lock:
                still_there = item_id in self._items
            if not still_there:
                return

            stem = Path(filename).stem
            out_path = OUTPUT_DIR / f"{stem}Output.xlsx"
            write_xlsx(output_rows, input_columns, out_path)

            final_status = "stopped" if stopped_mid_run else "done"
            snap = self._update_item(item_id, output_path=str(out_path), status=final_status)
            if snap is not None:
                self._broadcast({
                    "type": "item_done" if final_status == "done" else "item_stopped",
                    "item_id": item_id,
                    "output_path": snap["output_path"],
                    "clean": snap["clean"],
                    "flagged": snap["flagged"],
                    "keep": snap["keep"],
                    "review": snap["review"],
                    "drop": snap["drop"],
                    "total": snap["total"],
                    "processed": snap["processed"],
                })

        except Exception as e:
            self._update_item(item_id, status="error", error=str(e))
            self._broadcast({
                "type": "item_error",
                "item_id": item_id,
                "error": str(e),
            })
        finally:
            self._cleanup_upload(src_path)

    @staticmethod
    def _cleanup_upload(src_path: str) -> None:
        """Remove the uploaded CSV file. Best effort; never raises."""
        if not src_path:
            return
        with contextlib.suppress(Exception):
            p = Path(src_path)
            if p.exists() and p.is_file():
                p.unlink()


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


def _parse_year(s: str) -> str:
    """Parse a year out of common date formats. 'Oct 30, 2019' -> '2019'."""
    if not s or s.lower() in ("nan", "none", ""):
        return ""
    s = s.strip()
    m = re.search(r"(19|20)\d{2}", s)
    return m.group(0) if m else ""


# Per-source priority for the live-log roll-up. Higher number wins when
# a source has multiple hits across multiple releases.
_SOURCE_PRIORITY = {
    "MAJOR": 5,
    "LICENSED": 4,
    "THIRDPARTY": 3,
    "VARIANT": 2,
    "DISTRIBUTOR": 1,
    "EMPTY": 0,
}


def _source_family(source: str) -> str:
    """Collapse 'iTunes (P-line)' / 'iTunes (licensee)' / 'iTunes' into
    a single 'iTunes' bucket so the per-source view shows one line per
    real platform."""
    if source.startswith("iTunes"):
        return "iTunes"
    return source


def _summarize_per_source(evaluations) -> list:
    """
    Roll the per-(source, label) evaluations into one summary entry per
    source family. The summary chooses the worst hit per source. Returns
    a list of dicts in display order: Chartmetric, iTunes, Deezer,
    Discogs (sources not present are skipped).
    """
    by_source: dict = {}
    for ev in evaluations:
        family = _source_family(ev.source)
        cur = by_source.get(family)
        if cur is None or _SOURCE_PRIORITY.get(ev.status, 0) > _SOURCE_PRIORITY.get(cur.status, 0):
            by_source[family] = ev

    order = ["Chartmetric", "iTunes", "Deezer", "Discogs"]
    out = []
    for family in order:
        ev = by_source.get(family)
        if ev is None:
            continue
        out.append({
            "source": family,
            "status": ev.status,
            "label": ev.label,
            "reason": ev.reason,
        })
    # Any unknown future source families: append at the end.
    for family, ev in by_source.items():
        if family in order:
            continue
        out.append({
            "source": family,
            "status": ev.status,
            "label": ev.label,
            "reason": ev.reason,
        })
    return out


# Singleton
manager = JobManager()