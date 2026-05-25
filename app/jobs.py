"""Background job runner.

A single global JobManager owns the queue and emits live events.
The Flask layer subscribes to an EventBus per job to stream SSE.
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import excel
from .audit import audit_artist
from .config import OUTPUT_DIR


@dataclass
class JobItem:
    job_id: str
    csv_path: Path
    display_name: str
    status: str = "queued"            # queued | running | done | error
    total: int = 0
    processed: int = 0
    flagged: int = 0
    clean: int = 0
    output_path: str | None = None
    clean_output_path: str | None = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None


class EventBus:
    """Fan-out queue of JSON-serializable events for SSE consumers."""

    def __init__(self) -> None:
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._history: list[dict] = []
        self._max_history = 1000

    def publish(self, event: dict) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            for q in list(self._subs):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=2000)
        with self._lock:
            for past in self._history:
                try:
                    q.put_nowait(past)
                except queue.Full:
                    break
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobItem] = {}
        self._order: list[str] = []
        self._bus = EventBus()
        self._worker_running = False
        self._lock = threading.Lock()

    @property
    def bus(self) -> EventBus:
        return self._bus

    def list_jobs(self) -> list[JobItem]:
        with self._lock:
            return [self._jobs[j] for j in self._order]

    def get_job(self, job_id: str) -> JobItem | None:
        with self._lock:
            return self._jobs.get(job_id)

    def add(self, csv_path: Path, display_name: str) -> JobItem:
        with self._lock:
            job = JobItem(
                job_id=uuid.uuid4().hex[:10],
                csv_path=csv_path,
                display_name=display_name,
            )
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
        self._bus.publish({"event": "job_added", "job": _job_dict(job)})
        return job

    def remove(self, job_id: str) -> bool:
        with self._lock:
            if job_id not in self._jobs:
                return False
            j = self._jobs[job_id]
            if j.status == "running":
                return False
            del self._jobs[job_id]
            self._order.remove(job_id)
        self._bus.publish({"event": "job_removed", "job_id": job_id})
        return True

    def clear_finished(self) -> int:
        removed = 0
        with self._lock:
            for jid in list(self._order):
                j = self._jobs[jid]
                if j.status in ("done", "error"):
                    del self._jobs[jid]
                    self._order.remove(jid)
                    removed += 1
        if removed:
            self._bus.publish({"event": "queue_cleared"})
        return removed

    def start(self) -> bool:
        with self._lock:
            if self._worker_running:
                return False
            self._worker_running = True
        threading.Thread(target=self._run_loop, daemon=True).start()
        return True

    # ---- internals ----

    def _next_queued(self) -> JobItem | None:
        with self._lock:
            for jid in self._order:
                j = self._jobs[jid]
                if j.status == "queued":
                    return j
            return None

    def _run_loop(self) -> None:
        try:
            while True:
                job = self._next_queued()
                if job is None:
                    break
                self._run_job(job)
        finally:
            with self._lock:
                self._worker_running = False
            self._bus.publish({"event": "queue_done"})

    def _run_job(self, job: JobItem) -> None:
        job.status = "running"
        job.started_at = time.time()
        self._bus.publish({"event": "job_started", "job": _job_dict(job)})

        try:
            df = pd.read_csv(job.csv_path)
            df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
            if "Artist" not in df.columns:
                raise ValueError("CSV is missing required 'Artist' column")
            if "Spotify Links" in df.columns:
                df["Spotify Links"] = df["Spotify Links"].apply(
                    lambda x: x.split(",")[0].strip() if isinstance(x, str) else x
                )

            with self._lock:
                job.total = len(df)
            self._bus.publish({"event": "job_total",
                              "job_id": job.job_id, "total": job.total})

            results: list[dict] = []
            for idx, row in df.iterrows():
                artist = str(row.get("Artist", "")).strip()
                cm_label = str(row.get("Associated Labels", "")).strip()

                self._bus.publish({
                    "event": "artist_start",
                    "job_id": job.job_id,
                    "index": int(idx) + 1,
                    "total": job.total,
                    "artist": artist,
                })

                try:
                    audit = audit_artist(artist, cm_label)
                except Exception as e:
                    self._bus.publish({
                        "event": "artist_error",
                        "job_id": job.job_id,
                        "artist": artist,
                        "error": str(e),
                    })
                    audit = None

                if audit is None:
                    out = {
                        "itunes_pline": "error",
                        "itunes_owners": "error",
                        "itunes_licensee": "",
                        "deezer_labels": "error",
                        "discogs_labels": "error",
                        "ever_signed": "no",
                        "has_licensing": "no",
                        "likely_self_imprint": "no",
                        "earliest_year": "",
                        "flag": "ERROR during lookup",
                        "verdict": "FLAGGED",
                        "ai_reason": "Audit failed for this row; rerun.",
                    }
                    verdict = "FLAGGED"
                else:
                    out = audit.to_row()
                    verdict = audit.verdict

                results.append(out)

                with self._lock:
                    job.processed += 1
                    if verdict == "CLEAN":
                        job.clean += 1
                    else:
                        job.flagged += 1
                    snapshot = (job.processed, job.total,
                                job.flagged, job.clean)

                self._bus.publish({
                    "event": "artist_done",
                    "job_id": job.job_id,
                    "index": snapshot[0],
                    "total": snapshot[1],
                    "artist": artist,
                    "verdict": verdict,
                    "reason": out["ai_reason"],
                    "flag": out["flag"],
                    "pline": out["itunes_pline"],
                    "licensee": out.get("itunes_licensee", ""),
                    "earliest_year": out.get("earliest_year", ""),
                    "self_imprint": out.get("likely_self_imprint", "no"),
                    "deezer_labels": out["deezer_labels"],
                    "discogs_labels": out["discogs_labels"],
                    "running_clean": snapshot[3],
                    "running_flagged": snapshot[2],
                })

            df["Apple P-Line"] = [r["itunes_pline"] for r in results]
            df["Apple Owners"] = [r["itunes_owners"] for r in results]
            df["Apple Licensed-To"] = [r["itunes_licensee"] for r in results]
            df["Deezer Labels Found"] = [r["deezer_labels"] for r in results]
            df["Discogs Labels Found"] = [r["discogs_labels"] for r in results]
            df["First Release Year"] = [r["earliest_year"] for r in results]
            df["Ever Signed"] = [r["ever_signed"] for r in results]
            df["Has Licensing"] = [r["has_licensing"] for r in results]
            df["Likely Self-Imprint"] = [r["likely_self_imprint"] for r in results]
            df["Flag"] = [r["flag"] for r in results]
            df["AI Verdict"] = [r["verdict"] for r in results]
            df["AI Reason"] = [r["ai_reason"] for r in results]

            stem = job.csv_path.stem
            out_path = OUTPUT_DIR / f"{stem}Output.xlsx"
            clean_path = OUTPUT_DIR / f"{stem}OutputCleanOnly.xlsx"
            excel.write(df, out_path)
            excel.write(df, clean_path, clean_only=True)
            with self._lock:
                job.output_path = str(out_path)
                job.clean_output_path = str(clean_path)
                job.status = "done"
                job.finished_at = time.time()
            self._bus.publish({"event": "job_done", "job": _job_dict(job)})

        except Exception as e:
            with self._lock:
                job.status = "error"
                job.error = str(e)
                job.finished_at = time.time()
            self._bus.publish({"event": "job_error", "job": _job_dict(job)})


def _job_dict(j: JobItem) -> dict:
    return {
        "job_id": j.job_id,
        "name": j.display_name,
        "status": j.status,
        "total": j.total,
        "processed": j.processed,
        "flagged": j.flagged,
        "clean": j.clean,
        "output_path": j.output_path,
        "clean_output_path": j.clean_output_path,
        "error": j.error,
    }


# Singleton
MANAGER = JobManager()
