"""Job manager — queue CSV files, process artists, broadcast SSE events.

Key features:
- Incremental xlsx writes every 5 artists (export always has something)
- Cooperative stop (finishes current artist, writes partial output)
- Error recovery (crashes don't lose already-processed rows)
- Thread-safe counter mutations
- Tolerant CSV header matching
"""
import re
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue, Full
from typing import Optional, List

import pandas as pd

from app import config, audit as audit_mod, excel


# ---------------------------------------------------------------------------
# Header aliases — tolerant matching for various Chartmetric export formats
# ---------------------------------------------------------------------------
_HEADER_ALIASES = {
    "artist": ["artist", "artist name", "performer", "name"],
    "associated_labels": ["associated labels", "label", "associated label", "labels"],
    "spotify_links": ["spotify links", "spotify link", "spotify url", "spotify"],
    "first_release_date": ["first release date", "first release", "earliest release"],
}


def _normalise_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to canonical names using alias matching."""
    col_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        for canonical, aliases in _HEADER_ALIASES.items():
            if cl in aliases:
                col_map[col] = canonical
                break
    if col_map:
        df = df.rename(columns=col_map)
    return df


def _parse_date_year(val) -> Optional[int]:
    """Parse various date formats to extract year."""
    if pd.isna(val) or not val:
        return None
    s = str(val).strip()
    # ISO: 2024-03-15
    m = re.match(r"(\d{4})-\d{2}-\d{2}", s)
    if m:
        return int(m.group(1))
    # Chartmetric: "Oct 30, 2019"
    m = re.search(r"(\d{4})", s)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Job item dataclass
# ---------------------------------------------------------------------------

@dataclass
class JobItem:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    filename: str = ""
    path: Optional[Path] = None
    status: str = "queued"  # queued, running, done, stopped, error
    error: str = ""
    processed: int = 0
    total: int = 0
    keep: int = 0
    review: int = 0
    drop: int = 0
    output_path: Optional[Path] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "error": self.error,
            "processed": self.processed,
            "total": self.total,
            "keep": self.keep,
            "review": self.review,
            "drop": self.drop,
            "has_output": self.output_path is not None and self.output_path.exists(),
        }


# ---------------------------------------------------------------------------
# Job Manager
# ---------------------------------------------------------------------------

class JobManager:
    def __init__(self):
        self._items: List[JobItem] = []
        self._lock = threading.Lock()
        self._running = False
        self._stop_requested = False
        self._subscribers: List[Queue] = []

    def subscribe(self) -> Queue:
        q = Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(q)
        # Send snapshot
        self._broadcast({"type": "snapshot", "items": [i.to_dict() for i in self._items]})
        return q

    def unsubscribe(self, q: Queue):
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def _broadcast(self, event: dict):
        with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except Full:
                    dead.append(q)
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass

    def add(self, filename: str, path: Path) -> JobItem:
        item = JobItem(filename=filename, path=path)
        with self._lock:
            self._items.append(item)
        self._broadcast({"type": "item_added", "item": item.to_dict()})
        return item

    def find(self, item_id: str) -> Optional[JobItem]:
        with self._lock:
            for item in self._items:
                if item.id == item_id:
                    return item
        return None

    def snapshot(self) -> List[dict]:
        with self._lock:
            return [i.to_dict() for i in self._items]

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_requested = False
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def stop(self):
        self._stop_requested = True

    def clear_done(self):
        with self._lock:
            self._items = [i for i in self._items if i.status in ("queued", "running")]
        self._broadcast({"type": "snapshot", "items": [i.to_dict() for i in self._items]})

    def _run_loop(self):
        try:
            while True:
                # Find next queued item
                nxt = None
                with self._lock:
                    if self._stop_requested:
                        break
                    for item in self._items:
                        if item.status == "queued":
                            nxt = item
                            break
                if nxt is None:
                    break
                try:
                    self._run_item(nxt)
                except Exception as e:
                    print(f"[WORKER ERROR] {nxt.filename}: {e}\n{traceback.format_exc()}", flush=True)
                    with self._lock:
                        nxt.status = "error"
                        nxt.error = str(e)
                    self._broadcast({"type": "item_error", "item": nxt.to_dict()})
        finally:
            with self._lock:
                self._running = False
            self._broadcast({"type": "queue_done"})

    def _run_item(self, item: JobItem):
        with self._lock:
            item.status = "running"
        self._broadcast({"type": "item_started", "item": item.to_dict()})

        # Read CSV
        try:
            df = pd.read_csv(str(item.path))
            df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
            df = _normalise_headers(df)
        except Exception as e:
            with self._lock:
                item.status = "error"
                item.error = f"CSV read failed: {e}"
            self._broadcast({"type": "item_error", "item": item.to_dict()})
            return

        # Find artist column
        artist_col = None
        for col in df.columns:
            if col.lower().strip() in ("artist", "artist name"):
                artist_col = col
                break
        if artist_col is None:
            with self._lock:
                item.status = "error"
                item.error = "No 'Artist' column found in CSV"
            self._broadcast({"type": "item_error", "item": item.to_dict()})
            return

        # Clean Spotify links (keep first only)
        sp_col = None
        for col in df.columns:
            if col.lower().strip() in ("spotify links", "spotify_links", "spotify link"):
                sp_col = col
                break
        if sp_col:
            df[sp_col] = df[sp_col].apply(
                lambda x: str(x).split(",")[0].strip() if pd.notna(x) else ""
            )

        total = len(df)
        with self._lock:
            item.total = total

        # Add audit columns (use object dtype to avoid pandas strict typing)
        for col in excel.AUDIT_COLUMNS:
            if col not in df.columns:
                df[col] = pd.Series([""] * total, dtype="object")

        # Process each artist
        cancelled = False
        for idx, row in df.iterrows():
            if self._stop_requested:
                cancelled = True
                break

            artist = str(row.get(artist_col, "")).strip()
            if not artist:
                with self._lock:
                    item.processed += 1
                continue

            # Get Chartmetric label and first release year
            cm_label = ""
            for col in ("associated_labels", "Associated Labels"):
                if col in row.index:
                    cm_label = str(row[col]) if pd.notna(row.get(col)) else ""
                    break

            cm_year = None
            for col in ("first_release_date", "First Release Date"):
                if col in row.index and pd.notna(row.get(col)):
                    cm_year = _parse_date_year(row[col])
                    break

            # Run the audit
            try:
                a = audit_mod.audit_artist(
                    artist=artist,
                    chartmetric_label=cm_label,
                    chartmetric_first_year=cm_year,
                )
            except Exception as e:
                print(f"[audit-error] {artist}: {e}\n{traceback.format_exc()}", flush=True)
                a = audit_mod.ArtistAudit(artist=artist)
                a.status = "REVIEW"
                a.status_reason = f"Audit error: {e}"

            # Write results to dataframe (str coercion for pandas compat)
            df.at[idx, "Status"] = str(a.status)
            df.at[idx, "Status Reason"] = str(a.status_reason)
            df.at[idx, "Earliest Year"] = str(a.earliest_year or "")
            df.at[idx, "AI Note"] = str(a.ai_note)

            # Build per-source label summaries
            itunes_labels = []
            deezer_labels = []
            discogs_labels = []
            for ev in a.evaluations:
                entry = f"{ev.label} [{ev.classification}]"
                if ev.source == "iTunes":
                    itunes_labels.append(entry)
                elif ev.source == "Deezer":
                    deezer_labels.append(entry)
                elif ev.source == "Discogs":
                    discogs_labels.append(entry)

            df.at[idx, "iTunes Labels"] = str(" | ".join(itunes_labels) if itunes_labels else "")
            df.at[idx, "Deezer Labels"] = str(" | ".join(deezer_labels) if deezer_labels else "")
            df.at[idx, "Discogs Labels"] = str(" | ".join(discogs_labels) if discogs_labels else "")

            # Update counters
            with self._lock:
                item.processed += 1
                if a.status == "KEEP":
                    item.keep += 1
                elif a.status == "REVIEW":
                    item.review += 1
                else:
                    item.drop += 1

            # Build per-source payload for SSE
            sources_payload = {"iTunes": [], "Deezer": [], "Discogs": [], "Chartmetric": []}
            for ev in a.evaluations:
                if ev.source in sources_payload:
                    sources_payload[ev.source].append({
                        "label": ev.label,
                        "classification": ev.classification,
                        "title": ev.title or "",
                        "year": ev.year,
                    })

            self._broadcast({
                "type": "artist_done",
                "item_id": item.id,
                "artist": artist,
                "status": a.status,
                "status_reason": a.status_reason,
                "sources": sources_payload,
                "earliest_year": a.earliest_year,
                "ai_note": a.ai_note,
                "processed": item.processed,
                "total": item.total,
                "keep": item.keep,
                "review": item.review,
                "drop": item.drop,
            })

            # Incremental xlsx write every 5 artists
            if item.processed % 5 == 0 or item.processed == item.total:
                self._write_partial(item, df)

        # Final write
        self._write_partial(item, df)

        # Set final status
        with self._lock:
            if cancelled:
                item.status = "stopped"
            else:
                item.status = "done"

        event_type = "item_stopped" if cancelled else "item_done"
        self._broadcast({"type": event_type, "item": item.to_dict()})

        # Cleanup upload
        self._cleanup_upload(item.path)

    def _write_partial(self, item: JobItem, df: pd.DataFrame):
        """Write whatever rows have been processed so far."""
        try:
            out_dir = config.OUTPUT_DIR
            stem = Path(item.filename).stem
            out_path = out_dir / f"{stem}Output.xlsx"
            processed_df = df.iloc[:item.processed].copy()
            excel.write_xlsx(processed_df, out_path)
            with self._lock:
                item.output_path = out_path
        except Exception as e:
            print(f"[partial-write] {item.filename}: {e}\n{traceback.format_exc()}", flush=True)

    def _cleanup_upload(self, path: Optional[Path]):
        """Remove the uploaded CSV after processing."""
        if path and path.exists():
            try:
                path.unlink()
            except Exception:
                pass
