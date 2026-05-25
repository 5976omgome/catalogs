"""Flask server exposing the audit pipeline to a local browser UI."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from flask_cors import CORS

from . import ai, cache
from .config import OUTPUT_DIR, PORT, UPLOAD_DIR
from .jobs import MANAGER, _job_dict
from .sources import discogs


def create_app() -> Flask:
    base = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(base / "templates"),
        static_folder=str(base / "static"),
    )
    CORS(app)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify({
            "ai_provider": ai.provider_name(),
            "ai_configured": ai.is_configured(),
            "discogs_configured": discogs.is_configured(),
            "output_dir": str(OUTPUT_DIR),
            "jobs": [_job_dict(j) for j in MANAGER.list_jobs()],
        })

    @app.post("/api/upload")
    def upload():
        if "files" not in request.files:
            return jsonify({"error": "no files"}), 400
        added = []
        for f in request.files.getlist("files"):
            if not f.filename:
                continue
            if not f.filename.lower().endswith(".csv"):
                continue
            safe = _safe_filename(f.filename)
            dst = UPLOAD_DIR / f"{int(time.time()*1000)}_{safe}"
            f.save(dst)
            job = MANAGER.add(dst, f.filename)
            added.append(_job_dict(job))
        return jsonify({"added": added})

    @app.post("/api/run")
    def run():
        started = MANAGER.start()
        return jsonify({"started": started})

    @app.post("/api/jobs/<job_id>/remove")
    def remove(job_id: str):
        ok = MANAGER.remove(job_id)
        return jsonify({"removed": ok})

    @app.post("/api/jobs/clear-finished")
    def clear_finished():
        n = MANAGER.clear_finished()
        return jsonify({"cleared": n})

    @app.post("/api/cache/clear")
    def cache_clear():
        n = cache.clear()
        return jsonify({"cleared": n})

    @app.get("/api/download/<job_id>")
    def download(job_id: str):
        for j in MANAGER.list_jobs():
            if j.job_id == job_id and j.output_path:
                return send_file(j.output_path, as_attachment=True)
        return jsonify({"error": "not found"}), 404

    @app.post("/api/open-output")
    def open_output():
        """Open the Outputs folder in the host OS file manager."""
        path = str(OUTPUT_DIR)
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            elif platform.system() == "Windows":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])
            return jsonify({"opened": True})
        except Exception as e:
            return jsonify({"opened": False, "error": str(e)}), 500

    @app.get("/api/stream")
    def stream():
        """Server-Sent Events feed for live UI updates."""
        def gen():
            q = MANAGER.bus.subscribe()
            try:
                # initial snapshot so the UI hydrates immediately
                yield _sse({
                    "event": "snapshot",
                    "jobs": [_job_dict(j) for j in MANAGER.list_jobs()],
                })
                last_ping = time.time()
                while True:
                    try:
                        ev = q.get(timeout=15)
                        yield _sse(ev)
                    except Exception:
                        # keepalive
                        if time.time() - last_ping > 15:
                            yield ": ping\n\n"
                            last_ping = time.time()
            finally:
                MANAGER.bus.unsubscribe(q)

        return Response(gen(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        })

    return app


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _safe_filename(name: str) -> str:
    keep = "-_.() "
    return "".join(c for c in name if c.isalnum() or c in keep).strip() or "upload.csv"


def run_server() -> None:
    """Production-ish run with waitress (works on Windows + Mac)."""
    from waitress import serve
    app = create_app()
    print(f"Catalog Audit running at http://127.0.0.1:{PORT}")
    serve(app, host="127.0.0.1", port=PORT, threads=8, _quiet=True)


if __name__ == "__main__":
    run_server()
