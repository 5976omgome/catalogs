"""Flask server — routes for upload, queue control, SSE stream, export, settings.

SSE note: does NOT set 'Connection' header (that was the hop-by-hop crash
on Waitress). Waitress handles keep-alive/close itself.
"""
import json
import time
import uuid
from pathlib import Path

from flask import Flask, request, Response, jsonify, send_file

from app import config, excel
from app.jobs import JobManager

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB max upload

_manager = JobManager()


def get_manager() -> JobManager:
    return _manager


# ---------------------------------------------------------------------------
# Static / index
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return app.send_static_file("index.html")


# ---------------------------------------------------------------------------
# Settings (API keys)
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    store = config.keys_store()
    s = store.status()
    return jsonify({
        "discogs_set": s["discogs_token"]["set"],
        "groq_set": s["groq_api_key"]["set"],
        "gemini_set": s["gemini_api_key"]["set"],
    })


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    store = config.keys_store()
    return jsonify(store.status())


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "invalid body"}), 400
    store = config.keys_store()
    for key in ("discogs_token", "groq_api_key", "gemini_api_key"):
        if key in data:
            val = str(data[key]).strip()
            if val:
                store.set(key, val)
            else:
                store.clear(key)
    return jsonify(store.status())


@app.route("/api/settings/clear", methods=["POST"])
def api_settings_clear():
    store = config.keys_store()
    store.clear()
    return jsonify(store.status())


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "no filename"}), 400

    # Validate extension
    ext = Path(f.filename).suffix.lower()
    if ext not in (".csv", ".tsv"):
        return jsonify({"error": "only .csv and .tsv files accepted"}), 400

    # Save with UUID prefix to avoid collisions
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
    dest = config.UPLOAD_DIR / safe_name
    f.save(str(dest))

    mgr = get_manager()
    item = mgr.add(filename=f.filename, path=dest)
    return jsonify(item.to_dict()), 201


# ---------------------------------------------------------------------------
# Queue control
# ---------------------------------------------------------------------------

@app.route("/api/queue/start", methods=["POST"])
def api_queue_start():
    mgr = get_manager()
    mgr.start()
    return jsonify({"ok": True})


@app.route("/api/queue/stop", methods=["POST"])
def api_queue_stop():
    mgr = get_manager()
    mgr.stop()
    return jsonify({"ok": True})


@app.route("/api/queue/clear", methods=["POST"])
def api_queue_clear():
    mgr = get_manager()
    mgr.clear_done()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Download / Export
# ---------------------------------------------------------------------------

@app.route("/api/download/<item_id>")
def api_download(item_id: str):
    """Download the full output xlsx (works on running/stopped/error items too)."""
    mgr = get_manager()
    item = mgr.find(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404
    if not item.output_path or not item.output_path.exists():
        return jsonify({"error": "no output yet — run not started or no artists processed"}), 404
    return send_file(
        str(item.output_path),
        as_attachment=True,
        download_name=item.output_path.name,
    )


@app.route("/api/export/<item_id>/<filter_name>")
def api_export(item_id: str, filter_name: str):
    """Export a filtered subset of the output xlsx."""
    mgr = get_manager()
    item = mgr.find(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404
    if not item.output_path or not item.output_path.exists():
        return jsonify({"error": "no output yet"}), 404

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
        try:
            dst.unlink(missing_ok=True)
        except Exception:
            pass
        return jsonify({"error": "no rows match this filter"}), 404

    return send_file(str(dst), as_attachment=True, download_name=dst.name)


@app.route("/api/queue/stop_and_export/<item_id>")
def api_stop_and_export(item_id: str):
    """Safety net: stop the run AND download whatever's been processed."""
    mgr = get_manager()
    item = mgr.find(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404

    mgr.stop()

    # Give worker up to 2s to flush final checkpoint
    for _ in range(20):
        if item.output_path and item.output_path.exists():
            break
        time.sleep(0.1)

    if not item.output_path or not item.output_path.exists():
        return jsonify({"error": "no output yet"}), 404

    return send_file(
        str(item.output_path),
        as_attachment=True,
        download_name=item.output_path.name,
    )


# ---------------------------------------------------------------------------
# SSE stream — no Connection header (that was the Waitress crash)
# ---------------------------------------------------------------------------

@app.route("/api/stream")
def api_stream():
    """Server-Sent Events stream for live progress updates."""
    mgr = get_manager()
    q = mgr.subscribe()

    def generate():
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except Exception:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except GeneratorExit:
            pass
        finally:
            mgr.unsubscribe(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            # NOTE: Do NOT set 'Connection' header here.
            # Waitress (WSGI) rejects hop-by-hop headers from the app.
        },
    )
