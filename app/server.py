"""Flask app: routes, SSE stream, settings, queue control, exports."""
from __future__ import annotations

import json
import queue
import time
import uuid
from pathlib import Path
from typing import Iterator

from flask import Flask, Response, jsonify, request, send_file, stream_with_context

from . import config, excel, keys
from .jobs import get_manager

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB
_ALLOWED_EXTS = {".csv", ".tsv"}


# --------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------
@app.route("/")
def index() -> Response:
    static_dir = Path(app.static_folder)
    return send_file(static_dir / "index.html")


# --------------------------------------------------------------------------
# Status (used by the front-end to render the keys-set pills)
# --------------------------------------------------------------------------
@app.route("/api/status")
def api_status() -> Response:
    s = keys.status()
    return jsonify({
        "discogs_set": s["discogs_token"]["set"],
        "groq_set": s["groq_api_key"]["set"],
        "gemini_set": s["gemini_api_key"]["set"],
    })


# --------------------------------------------------------------------------
# Settings (key management) — never echoes secrets
# --------------------------------------------------------------------------
@app.route("/api/settings", methods=["GET"])
def api_settings_get() -> Response:
    return jsonify(keys.status())


@app.route("/api/settings", methods=["POST"])
def api_settings_post() -> Response:
    try:
        body = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400
    if not isinstance(body, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
    try:
        keys.update_keys(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(keys.status())


@app.route("/api/settings/clear", methods=["POST"])
def api_settings_clear() -> Response:
    keys.clear_all()
    return jsonify(keys.status())


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------
@app.route("/api/upload", methods=["POST"])
def api_upload() -> Response:
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "empty filename"}), 400
    name_only = Path(f.filename).name  # strip any dir components
    ext = Path(name_only).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        return jsonify({"error": f"unsupported extension {ext}"}), 400
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(name_only).stem}{ext}"
    dst = config.UPLOAD_DIR / safe_name
    f.save(str(dst))
    item = get_manager().add(filename=name_only, path=dst)
    return jsonify({"ok": True, "item": item.to_dict()})


# --------------------------------------------------------------------------
# Queue control
# --------------------------------------------------------------------------
@app.route("/api/queue/start", methods=["POST"])
def api_start() -> Response:
    started = get_manager().start()
    return jsonify({"ok": True, "started": started})


@app.route("/api/queue/stop", methods=["POST"])
def api_stop() -> Response:
    stopped = get_manager().stop()
    return jsonify({"ok": True, "stopping": stopped})


@app.route("/api/queue/clear", methods=["POST"])
def api_clear() -> Response:
    get_manager().clear()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Download (full output) and filtered Export
# --------------------------------------------------------------------------
@app.route("/api/download/<item_id>")
def api_download(item_id: str) -> Response:
    item = get_manager().find(item_id)
    if not item or not item.output_path or not item.output_path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(
        str(item.output_path),
        as_attachment=True,
        download_name=item.output_path.name,
    )


@app.route("/api/export/<item_id>/<filter_name>")
def api_export(item_id: str, filter_name: str) -> Response:
    item = get_manager().find(item_id)
    if not item or not item.output_path or not item.output_path.exists():
        return jsonify({"error": "not found"}), 404
    f = filter_name.lower()
    if f == "keep":
        statuses = ["KEEP"]
    elif f == "review":
        statuses = ["REVIEW"]
    elif f == "drops":
        statuses = ["DROP"]
    elif f == "all":
        statuses = ["ALL"]
    else:
        return jsonify({"error": "filter must be keep|review|drops|all"}), 400

    stem = item.output_path.stem
    dst = config.OUTPUT_DIR / f"{stem}-{f}.xlsx"
    try:
        kept = excel.filter_xlsx_by_status(item.output_path, dst, statuses)
    except Exception as e:
        return jsonify({"error": f"export failed: {e}"}), 500
    if kept == 0:
        # Don't leave an empty file lying around
        try:
            dst.unlink(missing_ok=True)
        except Exception:
            pass
        return jsonify({"error": "no rows match this filter"}), 404
    return send_file(str(dst), as_attachment=True, download_name=dst.name)


# --------------------------------------------------------------------------
# SSE stream — note: do NOT set Connection: keep-alive (hop-by-hop, banned
# by WSGI/PEP 3333 and rejected by Waitress)
# --------------------------------------------------------------------------
def _sse_stream() -> Iterator[bytes]:
    mgr = get_manager()
    q = mgr.subscribe()
    try:
        # initial heartbeat so the client unblocks immediately
        yield b": connected\n\n"
        last_heartbeat = time.time()
        while True:
            try:
                event = q.get(timeout=1.0)
            except queue.Empty:
                event = None
            if event is not None:
                payload = json.dumps(event)
                yield f"data: {payload}\n\n".encode("utf-8")
            now = time.time()
            if now - last_heartbeat > 15:
                yield b": heartbeat\n\n"
                last_heartbeat = now
    except GeneratorExit:
        pass
    finally:
        mgr.unsubscribe(q)


@app.route("/api/stream")
def api_stream() -> Response:
    headers = {
        "Cache-Control": "no-cache, no-store",
        "X-Accel-Buffering": "no",
        # NOT setting Content-Encoding or Connection — those are hop-by-hop
        # and Waitress will assert them out.
    }
    return Response(stream_with_context(_sse_stream()),
                    mimetype="text/event-stream", headers=headers)
