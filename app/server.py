"""Flask server with SSE streaming.

CRITICAL: The /api/stream endpoint must NOT set a 'Connection' header.
'Connection' is a hop-by-hop header per RFC 7230 / PEP 3333; WSGI servers
like Waitress raise AssertionError if applications try to set it.
"""
import queue
import uuid
from pathlib import Path
from typing import Iterator

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

from . import config, keys
from .config import BASE_DIR, OUTPUT_DIR
from .jobs import manager

STATIC_DIR = BASE_DIR / "static"

# Keys we accept on POST /api/settings
_KEY_FIELDS = ("discogs_token", "groq_api_key", "gemini_api_key")

# Upload limits
_MAX_UPLOAD_BYTES = 32 * 1024 * 1024  # 32 MB - generous for CSV
_ALLOWED_EXTS = {".csv", ".tsv"}


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = _MAX_UPLOAD_BYTES

    @app.route("/")
    def index():
        return send_from_directory(str(STATIC_DIR), "index.html")

    @app.route("/api/status")
    def status():
        # Live, per-call - so a Save on the Settings card flips the pills
        # immediately on the next status fetch without a restart.
        return jsonify({
            "discogs": bool(config.discogs_token()),
            "groq": bool(config.groq_api_key()),
            "gemini": bool(config.gemini_api_key()),
            "output_dir": str(OUTPUT_DIR),
        })

    # ---- Settings: API keys ----

    @app.route("/api/settings", methods=["GET"])
    def settings_get():
        """
        Returns a per-key status report. Never returns the full secret -
        only a masked preview like 'tabx…TatO' and the source ('file',
        'env', or 'unset'). Safe to expose to the browser.
        """
        return jsonify({
            "keys": keys.status(),
            "storage_path": keys.storage_path(),
        })

    @app.route("/api/settings", methods=["POST"])
    def settings_set():
        """
        Accepts a JSON body with any of:
          - "discogs_token", "groq_api_key", "gemini_api_key"

        Semantics per field:
          - omitted     -> leave unchanged
          - empty ""    -> clear
          - non-empty   -> save

        Response is the same shape as GET (masked status). The full secret
        is never echoed back. Bodies arriving as form data are also accepted
        for graceful degradation when JS is disabled.
        """
        body = request.get_json(silent=True)
        if body is None:
            body = request.form.to_dict() if request.form else {}
        if not isinstance(body, dict):
            return jsonify({"error": "invalid body"}), 400

        updates = {}
        for field in _KEY_FIELDS:
            if field in body:
                v = body.get(field)
                if v is None:
                    continue
                # Normalize: trim whitespace; an empty string clears.
                updates[field] = str(v).strip()

        if not updates:
            return jsonify({
                "ok": True,
                "updated": [],
                "keys": keys.status(),
                "storage_path": keys.storage_path(),
            })

        keys.set_many(updates)

        # Compute which fields actually changed source state for a useful response.
        return jsonify({
            "ok": True,
            "updated": sorted(updates.keys()),
            "keys": keys.status(),
            "storage_path": keys.storage_path(),
        })

    # ---- Queue & files ----

    @app.route("/api/upload", methods=["POST"])
    def upload():
        if "files" not in request.files:
            return jsonify({"error": "no files"}), 400
        added = []
        skipped = []
        upload_dir = BASE_DIR / ".uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        for f in request.files.getlist("files"):
            if not f.filename:
                continue
            # Path(...).name strips any directory components -> no traversal.
            safe_name = Path(f.filename).name
            ext = Path(safe_name).suffix.lower()
            if ext not in _ALLOWED_EXTS:
                skipped.append({"filename": safe_name, "reason": f"extension {ext or '<none>'} not allowed"})
                continue
            # UUID prefix prevents collisions between simultaneous uploads.
            dest = upload_dir / f"{uuid.uuid4().hex}_{safe_name}"
            f.save(str(dest))
            item = manager.add(filename=safe_name, path=str(dest))
            added.append(item.item_id)
        return jsonify({"added": added, "skipped": skipped})

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
        # Find the item via the public snapshot (no path traversal possible).
        for it in manager.snapshot():
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
