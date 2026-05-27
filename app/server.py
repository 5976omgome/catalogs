"""Flask server with SSE streaming.

CRITICAL: The /api/stream endpoint must NOT set a 'Connection' header.
'Connection' is a hop-by-hop header per RFC 7230 / PEP 3333; WSGI servers
like Waitress raise AssertionError if applications try to set it.
"""
import os
import queue
import time
from pathlib import Path
from typing import Iterator

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

from .config import (
    BASE_DIR, DISCOGS_TOKEN, GEMINI_API_KEY, GROQ_API_KEY, OUTPUT_DIR,
)
from .jobs import manager

STATIC_DIR = BASE_DIR / "static"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")

    @app.route("/")
    def index():
        return send_from_directory(str(STATIC_DIR), "index.html")

    @app.route("/api/status")
    def status():
        return jsonify({
            "discogs": bool(DISCOGS_TOKEN),
            "groq": bool(GROQ_API_KEY),
            "gemini": bool(GEMINI_API_KEY),
            "output_dir": str(OUTPUT_DIR),
        })

    @app.route("/api/upload", methods=["POST"])
    def upload():
        if "files" not in request.files:
            return jsonify({"error": "no files"}), 400
        added = []
        upload_dir = BASE_DIR / ".uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        for f in request.files.getlist("files"):
            if not f.filename:
                continue
            safe = Path(f.filename).name
            dest = upload_dir / f"{int(time.time()*1000)}_{safe}"
            f.save(str(dest))
            item = manager.add(filename=safe, path=str(dest))
            added.append(item.item_id)
        return jsonify({"added": added})

    @app.route("/api/queue/start", methods=["POST"])
    def start_queue():
        manager.start()
        return jsonify({"ok": True})

    @app.route("/api/queue/clear", methods=["POST"])
    def clear_queue():
        manager.clear()
        return jsonify({"ok": True})

    @app.route("/api/queue/remove", methods=["POST"])
    def remove_item():
        body = request.get_json(silent=True) or {}
        item_id = body.get("item_id")
        if item_id:
            manager.remove(item_id)
        return jsonify({"ok": True})

    @app.route("/api/download/<item_id>")
    def download(item_id):
        # NOTE: We don't expose path traversal - find by id
        for snap in [manager._snapshot()]:
            for it in snap:
                if it["item_id"] == item_id and it.get("output_path"):
                    p = Path(it["output_path"])
                    if p.exists():
                        return send_file(str(p), as_attachment=True)
        return jsonify({"error": "not found"}), 404

    @app.route("/api/stream")
    def stream():
        sub = manager.subscribe()

        def generate() -> Iterator[bytes]:
            try:
                # initial heartbeat
                yield b": connected\n\n"
                while True:
                    try:
                        msg = sub.q.get(timeout=15.0)
                        yield f"data: {msg}\n\n".encode("utf-8")
                    except queue.Empty:
                        # heartbeat to keep proxies happy
                        yield b": ping\n\n"
            except GeneratorExit:
                pass
            finally:
                manager.unsubscribe(sub)

        # CRITICAL: Do NOT set 'Connection' header here. It's hop-by-hop per
        # PEP 3333 and Waitress will assert. Cache-Control is enough to
        # prevent buffering by intermediate proxies.
        resp = Response(generate(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache, no-transform"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    return app
