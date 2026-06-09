"""Job manager — process ALL queued CSVs simultaneously, each with parallel artists.

Key features:
- ALL CSVs run at the same time (each gets its own worker thread)
- Artists within each CSV process 4-at-a-time (ThreadPoolExecutor)
- Incremental xlsx writes every 25 artists
- Cooperative stop per-item
- Error recovery
"""
import re
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue, Full
from typing import Optional, List

import pandas as pd

from app import config, audit as audit_mod, excel, csv_export

PARALLEL_ARTISTS = 4  # Artists processed simultaneously within one CSV

# ---------------------------------------------------------------------------
# Header aliases
# ---------------------------------------------------------------------------
_HEADER_ALIASES = {
    "artist": ["artist", "artist name", "performer", "name"],
    "associated_labels": ["associated labels", "label", "associated label", "labels"],
    "spotify_links": ["spotify links", "spotify link", "spotify url", "spotify"],
    "first_release_date": ["first release date", "first release", "earliest release"],
}


def _normalise_headers(df: pd.DataFrame) -> pd.DataFrame:
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
    if pd.isna(val) or not val:
        return None
    s = str(val).strip()
    m = re.match(r"(\d{4})-\d{2}-\d{2}", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{4})", s)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Job item
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
    started_at: Optional[float] = None  # epoch seconds — set at the running transition
    _stop: bool = field(default=False, repr=False)
    use_gemini: bool = field(default=True)   # Whether AI bridge runs for this item
    verbose: bool = field(default=True)       # Emit debug events (always on, UI toggle controls display)
    use_genius: bool = field(default=True)    # Pull socials from Genius (always on when key exists)

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
            "started_at": self.started_at,
            "use_gemini": self.use_gemini,
            "verbose": self.verbose,
            "use_genius": self.use_genius,
        }


# ---------------------------------------------------------------------------
# Job Manager — runs ALL items simultaneously
# ---------------------------------------------------------------------------

class JobManager:
    def __init__(self):
        self._items: List[JobItem] = []
        self._lock = threading.Lock()
        self._subscribers: List[Queue] = []
        self._active_threads: dict = {}  # item_id → Thread

    def subscribe(self) -> Queue:
        q = Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(q)
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
        """Start queued items — max 4 concurrent. Rest stay queued."""
        with self._lock:
            running_count = sum(1 for i in self._items if i.status == "running")
            available_slots = 4 - running_count
            if available_slots <= 0:
                return
            queued = [i for i in self._items if i.status == "queued"][:available_slots]
        for item in queued:
            if item.id not in self._active_threads:
                t = threading.Thread(target=self._run_item_safe, args=(item,), daemon=True)
                self._active_threads[item.id] = t
                t.start()

    def stop(self):
        """Signal ALL running items to stop."""
        with self._lock:
            for item in self._items:
                if item.status == "running":
                    item._stop = True

    def stop_item(self, item_id: str):
        """Signal a specific item to stop."""
        item = self.find(item_id)
        if item:
            item._stop = True

    def clear_done(self):
        with self._lock:
            self._items = [i for i in self._items if i.status in ("queued", "running")]
            # Clean up dead thread refs
            alive_ids = {i.id for i in self._items}
            self._active_threads = {k: v for k, v in self._active_threads.items() if k in alive_ids}
        self._broadcast({"type": "snapshot", "items": [i.to_dict() for i in self._items]})

    def _run_item_safe(self, item: JobItem):
        """Wrapper that catches all exceptions."""
        try:
            self._run_item(item)
        except Exception as e:
            print(f"[WORKER ERROR] {item.filename}: {e}\n{traceback.format_exc()}", flush=True)
            with self._lock:
                item.status = "error"
                item.error = str(e)
            self._broadcast({"type": "item_error", "item": item.to_dict()})
        finally:
            with self._lock:
                self._active_threads.pop(item.id, None)
            # Auto-start next queued item (max 4 concurrent)
            self.start()

    def _run_item(self, item: JobItem):
        with self._lock:
            item.status = "running"
            item.started_at = time.time()
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

        # Clean Spotify links
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

        # Add audit columns
        for col in excel.AUDIT_COLUMNS:
            if col not in df.columns:
                df[col] = pd.Series([""] * total, dtype="object")

        # --- PARALLEL artist processing ---
        cancelled = False

        def _audit_one(idx, row):
            """Audit one artist — runs in thread pool."""
            import time as _time
            artist = str(row.get(artist_col, "")).strip()
            if not artist:
                return idx, None, None, None

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

            # Verbose: track timing
            debug_info = None
            if item.verbose:
                debug_info = {"artist": artist, "steps": []}
                t0 = _time.time()

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

            if item.verbose and debug_info is not None:
                elapsed = _time.time() - t0
                debug_info["audit_time_ms"] = int(elapsed * 1000)
                debug_info["status"] = a.status
                debug_info["evals_count"] = len(a.evaluations)
                debug_info["steps"].append(f"audit: {int(elapsed*1000)}ms → {a.status}")

            # Genius socials — REMOVED from main audit loop.
            # Genius rate limits are too strict for parallel processing.
            # Use the separate "GENIUS RUN" button after main audit completes.
            socials = None

            return idx, a, socials, debug_info

        with ThreadPoolExecutor(max_workers=PARALLEL_ARTISTS) as executor:
            futures = {}
            row_iter = df.iterrows()

            # Submit initial batch
            for _ in range(min(PARALLEL_ARTISTS * 2, total)):
                try:
                    idx, row = next(row_iter)
                    futures[executor.submit(_audit_one, idx, row)] = idx
                except StopIteration:
                    break

            while futures:
                if item._stop:
                    cancelled = True
                    for f in futures:
                        f.cancel()
                    break

                done_futures = [f for f in list(futures) if f.done()]
                if not done_futures:
                    time.sleep(0.03)
                    continue

                for future in done_futures:
                    del futures[future]

                    try:
                        idx, a, socials, debug_info = future.result()
                    except Exception as e:
                        print(f"[worker-error] {e}", flush=True)
                        with self._lock:
                            item.processed += 1
                        continue

                    if a is None:
                        with self._lock:
                            item.processed += 1
                        continue

                    artist = a.artist

                    # Write to dataframe
                    df.at[idx, "Status"] = str(a.status)
                    df.at[idx, "Status Reason"] = str(a.status_reason)
                    df.at[idx, "Earliest Year"] = str(a.earliest_year or "")
                    df.at[idx, "AI Note"] = str(a.ai_note)

                    itunes_labels = []
                    deezer_labels = []
                    for ev in a.evaluations:
                        entry = f"{ev.label} [{ev.classification}]"
                        if ev.source == "iTunes":
                            itunes_labels.append(entry)
                        elif ev.source == "Deezer":
                            deezer_labels.append(entry)

                    df.at[idx, "iTunes Labels"] = str(" | ".join(itunes_labels) if itunes_labels else "")
                    df.at[idx, "Deezer Labels"] = str(" | ".join(deezer_labels) if deezer_labels else "")

                    # Genius socials → separate columns with full links
                    if socials:
                        if socials.get("instagram"):
                            handle = socials["instagram"].lstrip("@")
                            df.at[idx, "Instagram"] = f"https://instagram.com/{handle}"
                        if socials.get("facebook"):
                            fb = socials["facebook"]
                            if fb.startswith("http"):
                                df.at[idx, "Facebook"] = fb
                            else:
                                df.at[idx, "Facebook"] = f"https://facebook.com/{fb}"
                        if socials.get("youtube"):
                            yt = socials["youtube"]
                            df.at[idx, "YouTube"] = yt if yt.startswith("http") else f"https://youtube.com/{yt}"

                    with self._lock:
                        item.processed += 1
                        if a.status == "KEEP":
                            item.keep += 1
                        elif a.status == "REVIEW":
                            item.review += 1
                        else:
                            item.drop += 1

                    # SSE event
                    sources_payload = {"iTunes": [], "Deezer": [], "Chartmetric": []}
                    for ev in a.evaluations:
                        if ev.source in sources_payload:
                            sources_payload[ev.source].append({
                                "label": ev.label,
                                "classification": ev.classification,
                                "title": ev.title or "",
                                "year": ev.year,
                            })

                    event_data = {
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
                    }

                    # Add socials if available
                    if socials:
                        event_data["socials"] = socials

                    # Add debug info if verbose
                    if debug_info:
                        event_data["debug"] = debug_info

                    self._broadcast(event_data)

                    if item.processed % 25 == 0 or item.processed == item.total:
                        self._write_partial(item, df)

                # Submit more
                if not cancelled:
                    while len(futures) < PARALLEL_ARTISTS * 2:
                        try:
                            idx, row = next(row_iter)
                            futures[executor.submit(_audit_one, idx, row)] = idx
                        except StopIteration:
                            break

        # Final write
        self._write_partial(item, df)

        with self._lock:
            item.status = "stopped" if cancelled else "done"

        event_type = "item_stopped" if cancelled else "item_done"
        self._broadcast({"type": event_type, "item": item.to_dict()})

        # Cleanup upload
        if item.path and item.path.exists():
            try:
                item.path.unlink()
            except Exception:
                pass

    def _write_partial(self, item: JobItem, df: pd.DataFrame):
        try:
            out_dir = config.OUTPUT_DIR
            stem = Path(item.filename).stem
            out_path = out_dir / f"{stem}Output.csv"
            processed_df = df.iloc[:item.processed].copy() if item.processed < len(df) else df
            csv_export.write_csv(processed_df, out_path)
            with self._lock:
                item.output_path = out_path
        except Exception as e:
            print(f"[partial-write] {item.filename}: {e}", flush=True)
