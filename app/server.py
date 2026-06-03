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
        "groq_set": s["groq_api_key"]["set"],
        "gemini_set": s["gemini_api_key"]["set"],
        "genius_set": s["genius_token"]["set"],
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
    for key in ("groq_api_key", "gemini_api_key", "genius_token"):
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


@app.route("/api/export_all")
def api_export_all():
    """Merge ALL finished item outputs into one master xlsx."""
    mgr = get_manager()
    items_with_output = []
    with mgr._lock:
        for item in mgr._items:
            if item.output_path and item.output_path.exists():
                items_with_output.append(item)

    if not items_with_output:
        return jsonify({"error": "no finished outputs to merge"}), 404

    try:
        merged_path = excel.merge_all_outputs(
            [item.output_path for item in items_with_output],
            config.OUTPUT_DIR / "AllCombinedOutput.xlsx",
        )
    except Exception as e:
        return jsonify({"error": f"merge failed: {e}"}), 500

    return send_file(
        str(merged_path),
        as_attachment=True,
        download_name="AllCombinedOutput.xlsx",
    )


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
# Feedback — writes .md files to feedback/ folder, Groq AI cleanup
# ---------------------------------------------------------------------------

FEEDBACK_DIR = config.BASE_DIR / "feedback"
FEEDBACK_DIR.mkdir(exist_ok=True)


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """Submit feedback — writes a markdown file to feedback/ folder."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid body"}), 400

    category = (data.get("category") or "").strip().upper()
    if category not in ("BUG", "IDEA", "OTHER"):
        return jsonify({"error": "category must be BUG, IDEA, or OTHER"}), 400

    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    raw_text = (data.get("raw_text") or "").strip()
    ai_enhanced = bool(data.get("ai_enhanced", False))

    from datetime import datetime
    now = datetime.now()
    filename = f"{now.strftime('%m-%d.%H.%M')}.{category}.md"

    # Build markdown optimized for Claude parsing
    lines = [
        "---",
        f"category: {category}",
        f"date: {now.isoformat()}",
        f"platform: IGNITE VIRTUAL SCOUT",
        f"version: v5.0.0",
        f"ai_enhanced: {str(ai_enhanced).lower()}",
        "---",
        "",
        f"# {category}: {text.split(chr(10))[0][:80]}",
        "",
        text,
        "",
    ]

    if ai_enhanced and raw_text:
        lines.extend([
            "---",
            "",
            f"> **Original (raw):** {raw_text}",
            "",
        ])

    content = "\n".join(lines)
    filepath = FEEDBACK_DIR / filename
    filepath.write_text(content, encoding="utf-8")

    return jsonify({"ok": True, "file": filename}), 201


@app.route("/api/feedback/clean", methods=["POST"])
def api_feedback_clean():
    """Use Groq to clean up feedback text into an optimized Claude prompt."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid body"}), 400

    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    category = (data.get("category") or "OTHER").strip().upper()

    groq_key = config.groq_api_key()
    if not groq_key:
        return jsonify({"error": "Groq API key not configured. Add it in the API panel."}), 400

    category_context = {
        "BUG": "This is a bug report for IGNITE: VIRTUAL SCOUT, a Flask-based catalog intelligence platform. It processes CSV artist exports through iTunes, Deezer, Genius, Chartmetric, Groq, and Gemini APIs to verify catalog ownership for licensing/buyout opportunities.",
        "IDEA": "This is a feature idea for IGNITE: VIRTUAL SCOUT, a Flask-based catalog intelligence platform that processes CSV artist exports through multiple APIs to verify catalog ownership.",
        "OTHER": "This is general feedback for IGNITE: VIRTUAL SCOUT, a Flask-based catalog intelligence platform.",
    }.get(category, "This is feedback for IGNITE: VIRTUAL SCOUT.")

    system_prompt = f"""You are an expert prompt engineer. Your job is to take raw user feedback and transform it into a perfectly structured, actionable prompt that Claude (Opus) can immediately research and act on.

Rules:
- Fix all grammar and spelling errors
- Clarify vague instructions — ask yourself what Claude would need to know to act on this
- Add context about WHAT part of the system this relates to
- Break complex feedback into clear, actionable steps
- For bugs: include what happened, what should happen, and where it occurs
- For ideas: include the goal, how it would work, and what it affects
- Structure with markdown headers and bullet points
- Keep it concise but complete — no fluff
- Do NOT wrap in code fences or add explanatory text around the output
- Output ONLY the enhanced prompt text, nothing else

{category_context}"""

    import requests as http_req
    try:
        resp = http_req.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {groq_key}",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        cleaned = result["choices"][0]["message"]["content"].strip()
        return jsonify({"ok": True, "cleaned": cleaned})
    except http_req.exceptions.Timeout:
        return jsonify({"error": "Groq API timeout — try again"}), 504
    except http_req.exceptions.HTTPError as e:
        msg = str(e)
        try:
            msg = e.response.json().get("error", {}).get("message", msg)
        except Exception:
            pass
        return jsonify({"error": f"Groq API error: {msg}"}), 502
    except Exception as e:
        return jsonify({"error": f"Groq request failed: {e}"}), 500


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
