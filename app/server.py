"""Flask server — routes for upload, queue control, SSE stream, export, settings.

SSE note: does NOT set 'Connection' header (that was the hop-by-hop crash
on Waitress). Waitress handles keep-alive/close itself.

The React SPA is served from app/static/dist/ for all non-API routes.
Legacy tool pages (index.html, genitractor.html) remain at /tools/* paths.
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, request, Response, jsonify, send_file, send_from_directory
from flask_login import login_required

from app import config, excel, csv_export
from app.jobs import JobManager
from app.database import init_db
from app.auth import auth_bp, login_manager
from app.settings_api import settings_bp
from app.stats_api import stats_bp
from app.artists_api import artists_bp
from app.reports_api import reports_bp

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder="static", static_url_path="/legacy-static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB max upload
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "ignite-virtual-scout-secret-2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_DURATION"] = 86400 * 30  # 30 days

# Initialize extensions
login_manager.init_app(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(artists_bp)
app.register_blueprint(reports_bp)

# Initialize database (creates tables + seeds admin)
init_db()

_manager = JobManager()

# Pass-level mutual exclusion for the Genitractor Genius extraction pass.
# Distinct from genius._genius_lock, which only paces individual request timing.
genius_pass_lock = threading.Lock()


def get_manager() -> JobManager:
    return _manager


# ---------------------------------------------------------------------------
# React SPA + Legacy tool pages
# ---------------------------------------------------------------------------

DIST_DIR = Path(__file__).parent / "static" / "dist"


@app.route("/")
def index():
    """Serve the React SPA (or fallback to legacy if dist/ not built yet)."""
    if (DIST_DIR / "index.html").exists():
        return send_from_directory(str(DIST_DIR), "index.html")
    return app.send_static_file("index.html")


@app.route("/genitractor")
def genitractor_page():
    return app.send_static_file("genitractor.html")


# Legacy tool pages served at /legacy/* for iframe embedding in React shell
@app.route("/legacy/chartporter")
def legacy_chartporter():
    return app.send_static_file("index.html")


@app.route("/legacy/genitractor")
def legacy_genitractor():
    return app.send_static_file("genitractor.html")


# Serve React SPA static assets (JS/CSS bundles from Vite build)
@app.route("/assets/<path:filename>")
def spa_assets(filename):
    return send_from_directory(str(DIST_DIR / "assets"), filename)


# Serve legacy tool static files (JS/CSS/HTML for iframe embedding)
@app.route("/legacy-static/<path:filename>")
def legacy_static_files(filename):
    return send_from_directory(str(Path(__file__).parent / "static"), filename)


# Serve logos and other public files from dist/
@app.route("/logos/<path:filename>")
def logos(filename):
    # Try dist first, then legacy static
    dist_logos = DIST_DIR / "logos" / filename
    if dist_logos.exists():
        return send_from_directory(str(DIST_DIR / "logos"), filename)
    return send_from_directory(str(Path(__file__).parent / "static" / "logos"), filename)


# SPA catch-all — serves React index.html for all frontend routes
# Must be AFTER all /api/* routes and legacy pages
@app.route("/login")
@app.route("/dashboard")
@app.route("/settings")
@app.route("/artists")
@app.route("/tools/chartporter")
@app.route("/tools/genitact")
@app.route("/tools/genitractor")
def spa_catchall():
    if (DIST_DIR / "index.html").exists():
        return send_from_directory(str(DIST_DIR), "index.html")
    return "React app not built. Run: cd frontend && npm run build", 404


# ---------------------------------------------------------------------------
# Settings (API keys)
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    store = config.keys_store()
    s = store.status()

    # Get key previews and genius count from DB
    genius_count = 0
    genius_preview = ""
    groq_preview = ""
    gemini_preview = ""
    try:
        from app.database import Session as DbSession, ApiKey
        from flask_login import current_user as cu
        session = DbSession()
        try:
            if hasattr(cu, 'id') and cu.is_authenticated:
                uid = cu.id
                gk = session.query(ApiKey).filter_by(user_id=uid, service="genius").all()
                genius_count = len(gk)
                if gk:
                    genius_preview = gk[0].key_value[:4]
                rk = session.query(ApiKey).filter_by(user_id=uid, service="groq").first()
                if rk:
                    groq_preview = rk.key_value[:4]
                mk = session.query(ApiKey).filter_by(user_id=uid, service="gemini").first()
                if mk:
                    gemini_preview = mk.key_value[:4]
        finally:
            DbSession.remove()
    except Exception:
        pass

    groq_val = config.groq_api_key() or ""
    gemini_val = config.gemini_api_key() or ""
    genius_val = config.genius_token() or ""

    return jsonify({
        "groq_set": s["groq_api_key"]["set"],
        "gemini_set": s["gemini_api_key"]["set"],
        "genius_set": s["genius_token"]["set"],
        "groq_preview": groq_preview or (groq_val[:4] if groq_val else ""),
        "gemini_preview": gemini_preview or (gemini_val[:4] if gemini_val else ""),
        "genius_preview": genius_preview or (genius_val[:4] if genius_val else ""),
        "genius_count": genius_count or (1 if genius_val else 0),
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
    """Download the full output CSV (works on running/stopped/error items too)."""
    mgr = get_manager()
    item = mgr.find(item_id)
    if not item:
        return jsonify({"error": "not found"}), 404
    if not item.output_path or not item.output_path.exists():
        return jsonify({"error": "no output yet — run not started or no artists processed"}), 404
    return send_file(
        str(item.output_path),
        mimetype="text/csv",
        as_attachment=True,
        download_name=item.output_path.name,
    )


@app.route("/api/export/<item_id>/<filter_name>")
def api_export(item_id: str, filter_name: str):
    """Export a filtered subset of the output as plain CSV."""
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
    dst = config.OUTPUT_DIR / f"{stem}-{f}.csv"
    try:
        kept = csv_export.filter_csv_by_status(item.output_path, dst, statuses)
    except Exception as e:
        return jsonify({"error": f"export failed: {e}"}), 500

    if kept == 0:
        try:
            dst.unlink(missing_ok=True)
        except Exception:
            pass
        return jsonify({"error": "no rows match this filter"}), 404

    return send_file(str(dst), mimetype="text/csv", as_attachment=True, download_name=dst.name)


@app.route("/api/export_all")
def api_export_all():
    """Merge ALL completed item outputs into one master CSV.

    Only items with status in {done, stopped} AND an existing output are merged,
    so a running item's mid-write checkpoint is never read (Concern H I/O safety).
    """
    mgr = get_manager()
    items_with_output = []
    with mgr._lock:
        for item in mgr._items:
            if item.status in ("done", "stopped") and item.output_path and item.output_path.exists():
                items_with_output.append(item)

    if not items_with_output:
        return jsonify({"error": "no finished outputs to merge"}), 404

    try:
        merged_path = csv_export.merge_all_csv(
            [item.output_path for item in items_with_output],
            config.OUTPUT_DIR / "AllCombinedOutput.csv",
        )
    except Exception as e:
        return jsonify({"error": f"merge failed: {e}"}), 500

    return send_file(
        str(merged_path),
        mimetype="text/csv",
        as_attachment=True,
        download_name="AllCombinedOutput.csv",
    )


@app.route("/api/queue/stop_and_export/<item_id>")
def api_stop_and_export(item_id: str):
    """Safety net: stop the run AND download whatever's been processed (as CSV)."""
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
        mimetype="text/csv",
        as_attachment=True,
        download_name=item.output_path.name,
    )


# ---------------------------------------------------------------------------
# GENITRACTOR — Contact extraction tool (Genius-only, separate from main audit)
# Processes CSVs to extract Instagram/Facebook via Genius API
# Exports a clean CSV with: Artist Name, Instagram, Facebook, Match Confidence
# ---------------------------------------------------------------------------

import csv
import io
import threading as _geni_threading
from queue import Queue as _GeniQueue, Full as _GeniFull

_geni_items = []
_geni_lock = _geni_threading.Lock()
_geni_subscribers = []
_geni_active_threads = {}
_geni_stop_flags = {}

# Periodic-pause configuration for large Genitractor runs (Concern D).
GENI_PAUSE_EVERY = 250    # pause after this many artists
GENI_PAUSE_SECONDS = 5    # sleep this many seconds at each pause

# Rate-limit recovery (Bug fix): when Genius rate-limits us past
# get_socials()'s own escalating backoff, RETRY THE SAME ARTIST after a cooldown
# instead of recording an empty result and moving on. The old behavior left
# rate-limited artists blank — and because RATE_LIMITED is never cached, a
# re-run "recovered" them, which is exactly why re-running a file yielded MORE
# contacts the second time. Retrying in-place makes a single pass complete and
# deterministic.
GENI_MAX_RL_RETRIES = 5   # max in-place retries per artist before giving up
GENI_RL_COOLDOWN = 30     # seconds to wait between those retries


def _genius_socials_resilient(artist_name, key=None, stop_check=None, on_cooldown=None):
    """Fetch Genius socials for one artist using a specific key, retrying the
    SAME artist (on the SAME key) through rate limits.

    ``genius.get_socials`` already applies escalating backoff internally and
    returns the RATE_LIMITED sentinel only when that is exhausted. Here we wait
    a longer cooldown and try the same artist again (up to GENI_MAX_RL_RETRIES)
    so the artist is never left blank just because a key was briefly throttling.

    Returns (socials_or_None, gave_up_rate_limited). When gave_up is True the
    caller can hand the artist to a DIFFERENT key (load-balanced failover).
    ``stop_check`` (callable) lets a cooldown abort promptly on user stop.
    """
    from app.sources import genius

    attempts = 0
    while True:
        socials = genius.get_socials(artist_name, key=key)
        if socials is not genius.RATE_LIMITED:
            return socials, False

        attempts += 1
        if attempts > GENI_MAX_RL_RETRIES:
            return None, True
        if on_cooldown:
            on_cooldown(attempts)
        # Cooperative cooldown — wake every second to honor a stop request.
        for _ in range(GENI_RL_COOLDOWN):
            if stop_check and stop_check():
                return None, True
            time.sleep(1)


def _gather_genius_keys():
    """Return every configured Genius token for load-balancing.

    Order: DB-stored slots 1-4 first (skipping any explicitly marked invalid),
    then the legacy keys.json / GENIUS_TOKEN env value as a fallback. Duplicates
    are removed while preserving order. Works for any count from 0 to 4+.
    """
    keys = []
    try:
        from app.database import Session, ApiKey
        s = Session()
        try:
            rows = (s.query(ApiKey)
                      .filter_by(service="genius")
                      .order_by(ApiKey.slot.asc())
                      .all())
            for r in rows:
                v = (r.key_value or "").strip()
                if v and r.is_valid is not False:  # None (unknown) is allowed
                    keys.append(v)
        finally:
            Session.remove()
    except Exception as e:
        print(f"[genitractor] DB key gather failed: {e}", flush=True)

    legacy = config.genius_token()
    if legacy:
        keys.append(legacy)

    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out

GENI_UPLOAD_DIR = config.BASE_DIR / ".geni_uploads"
GENI_UPLOAD_DIR.mkdir(exist_ok=True)
GENI_OUTPUT_DIR = config.BASE_DIR / "GeniOutputs"
GENI_OUTPUT_DIR.mkdir(exist_ok=True)


@app.route("/api/cross-status")
def api_cross_status():
    """Returns status of both tools for cross-tool progress bar.

    Sums ONLY currently-running items for both tools so live percentages are
    not inflated by finished work, and surfaces each tool's `started_at` (the
    min start time of its running items) for the cross-tool timer.
    """
    mgr = get_manager()

    # Chartporter status — running items only
    cp_processed = 0
    cp_total = 0
    cp_running = False
    cp_started_at = None
    with mgr._lock:
        for item in mgr._items:
            if item.status == "running":
                cp_running = True
                cp_processed += item.processed
                cp_total += item.total
                if item.started_at is not None:
                    cp_started_at = item.started_at if cp_started_at is None else min(cp_started_at, item.started_at)

    # Genitractor status — running items only
    gn_processed = 0
    gn_total = 0
    gn_running = False
    gn_started_at = None
    with _geni_lock:
        for item in _geni_items:
            if item["status"] == "running":
                gn_running = True
                gn_processed += item.get("processed", 0)
                gn_total += item.get("total", 0)
                st = item.get("started_at")
                if st is not None:
                    gn_started_at = st if gn_started_at is None else min(gn_started_at, st)

    return jsonify({
        "chartporter": {"running": cp_running, "processed": cp_processed, "total": cp_total, "started_at": cp_started_at},
        "genitractor": {"running": gn_running, "processed": gn_processed, "total": gn_total, "started_at": gn_started_at},
    })


def _geni_broadcast(event):
    with _geni_lock:
        dead = []
        for q in _geni_subscribers:
            try:
                q.put_nowait(event)
            except _GeniFull:
                dead.append(q)
        for q in dead:
            try:
                _geni_subscribers.remove(q)
            except ValueError:
                pass


@app.route("/api/genitractor/upload", methods=["POST"])
def geni_upload():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "no filename"}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in (".csv", ".tsv"):
        return jsonify({"error": "only .csv/.tsv"}), 400

    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
    dest = GENI_UPLOAD_DIR / safe_name
    f.save(str(dest))

    item = {
        "id": uuid.uuid4().hex[:12],
        "filename": f.filename,
        "path": str(dest),
        "status": "queued",
        "processed": 0,
        "total": 0,
        "found": 0,
        "started_at": None,
        "error": "",
    }
    with _geni_lock:
        _geni_items.append(item)
    _geni_broadcast({"type": "item_added", "item": item})
    return jsonify(item), 201


@app.route("/api/genitractor/start", methods=["POST"])
def geni_start():
    with _geni_lock:
        queued = [i for i in _geni_items if i["status"] == "queued"]
        running = sum(1 for i in _geni_items if i["status"] == "running")
        # Only 1 CSV at a time for Genitractor (Genius rate limit is global)
        if running >= 1:
            return jsonify({"ok": True, "started": 0, "message": "Already running — queued"})
        to_start = queued[:1]

    for item in to_start:
        _geni_stop_flags[item["id"]] = False
        t = _geni_threading.Thread(target=_geni_worker, args=(item,), daemon=True)
        _geni_active_threads[item["id"]] = t
        t.start()

    return jsonify({"ok": True, "started": len(to_start)})


@app.route("/api/genitractor/stop", methods=["POST"])
def geni_stop():
    with _geni_lock:
        for item in _geni_items:
            if item["status"] == "running":
                _geni_stop_flags[item["id"]] = True
    return jsonify({"ok": True})


@app.route("/api/genitractor/clear", methods=["POST"])
def geni_clear():
    """Clear all non-running Genitractor items and their contacts.

    Mirrors JobManager.clear_done(): keeps queued/running items, drops the
    rest, clears their `_contacts`, then broadcasts a fresh snapshot.
    Running items are never cleared.
    """
    global _geni_items
    with _geni_lock:
        kept = [i for i in _geni_items if i["status"] in ("queued", "running")]
        for i in kept:
            # Defensive: never carry stale contacts on a non-running kept item.
            if i["status"] != "running":
                i["_contacts"] = []
        _geni_items = kept
        alive_ids = {i["id"] for i in _geni_items}
        # Clean up dead thread/stop-flag refs
        for k in list(_geni_stop_flags.keys()):
            if k not in alive_ids:
                _geni_stop_flags.pop(k, None)
        snapshot_items = [_geni_item_dict(i) for i in _geni_items]
    _geni_broadcast({"type": "snapshot", "items": snapshot_items})
    return jsonify({"ok": True})


@app.route("/api/genitractor/import-from-chartporter", methods=["POST"])
def geni_import_from_chartporter():
    """Import files from Chartporter's queue into Genitractor.

    Reads only queued Chartporter items, copies each source file into
    GENI_UPLOAD_DIR with UUID prefix (preserving display filename),
    creates a Genitractor queue item per file, emits item_added SSE events,
    deduplicates by source path, and never mutates the Chartporter queue.
    """
    import shutil

    mgr = get_manager()
    imported = 0
    skipped = 0
    errors = 0

    # Read only queued Chartporter items (point-in-time snapshot)
    with mgr._lock:
        queued_items = [i for i in mgr._items if i.status == "queued"]

    # Collect existing source paths in Genitractor for dedup
    existing_paths = set()
    with _geni_lock:
        for gi in _geni_items:
            sp = gi.get("_source_path", "")
            if sp:
                existing_paths.add(sp)

    if not queued_items:
        return jsonify({"ok": True, "count": 0, "skipped": 0, "errors": 0,
                        "message": "Chartporter queue is empty"})

    for cp_item in queued_items:
        src_path = cp_item.path
        if src_path is None or not src_path.exists():
            errors += 1
            continue

        src_str = str(src_path)
        if src_str in existing_paths:
            skipped += 1
            continue

        # Copy file to GENI_UPLOAD_DIR with UUID prefix
        safe_name = f"{uuid.uuid4().hex[:8]}_{cp_item.filename}"
        dest = GENI_UPLOAD_DIR / safe_name
        try:
            shutil.copy2(str(src_path), str(dest))
        except Exception:
            errors += 1
            continue

        item = {
            "id": uuid.uuid4().hex[:12],
            "filename": cp_item.filename,
            "path": str(dest),
            "status": "queued",
            "processed": 0,
            "total": 0,
            "found": 0,
            "started_at": None,
            "error": "",
            "_source_path": src_str,  # for dedup
        }
        with _geni_lock:
            _geni_items.append(item)
            existing_paths.add(src_str)
        _geni_broadcast({"type": "item_added", "item": _geni_item_dict(item)})
        imported += 1

    return jsonify({"ok": True, "count": imported, "skipped": skipped, "errors": errors})


@app.route("/api/genitractor/export")
def geni_export():
    """Export all found contacts as a CSV (completed items only)."""
    with _geni_lock:
        all_contacts = []
        for item in _geni_items:
            # Only export from items that are not actively being written.
            if item["status"] == "running":
                continue
            # Sort by original row index so the CSV is always in input order,
            # regardless of the order parallel key-workers finished in.
            contacts = sorted(item.get("_contacts", []),
                              key=lambda c: c.get("_idx", 1 << 30))
            all_contacts.extend(contacts)

    if not all_contacts:
        return jsonify({"error": "no contacts found yet"}), 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Artist Name", "Instagram", "Facebook", "Match Confidence"])
    for c in all_contacts:
        writer.writerow([c.get("artist", ""), c.get("instagram", ""), c.get("facebook", ""), c.get("match_confidence", "")])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=Genitractor_Contacts.csv"},
    )


@app.route("/api/genitractor/stream")
def geni_stream():
    q = _GeniQueue(maxsize=200)
    with _geni_lock:
        _geni_subscribers.append(q)
    # Send snapshot
    snapshot = {"type": "snapshot", "items": [_geni_item_dict(i) for i in _geni_items]}
    try:
        q.put_nowait(snapshot)
    except _GeniFull:
        pass

    def generate():
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except Exception:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except GeneratorExit:
            pass
        finally:
            with _geni_lock:
                try:
                    _geni_subscribers.remove(q)
                except ValueError:
                    pass

    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _geni_item_dict(item):
    return {
        "id": item["id"],
        "filename": item["filename"],
        "status": item["status"],
        "processed": item["processed"],
        "total": item["total"],
        "found": item.get("found", 0),
        "started_at": item.get("started_at"),
        "error": item.get("error", ""),
    }


def _geni_worker(item):
    """Process one CSV — extract artist names, look up Genius socials one by one.

    All mutations of shared item fields (status/processed/total/_contacts/found)
    happen under `_geni_lock`; Genius network I/O happens OUTSIDE the lock.
    The whole extraction pass holds `genius_pass_lock` so it never runs
    concurrently with other Genius-consuming passes.
    """
    import pandas as pd
    from app.sources import genius

    try:
        with _geni_lock:
            item["status"] = "running"
            item["started_at"] = time.time()
        _geni_broadcast({"type": "item_started", "item": _geni_item_dict(item)})

        # Read CSV
        df = pd.read_csv(item["path"])
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

        # Find artist column
        artist_col = None
        for col in df.columns:
            if col.lower().strip() in ("artist", "artist name", "name"):
                artist_col = col
                break
        if not artist_col:
            # Try second column if first is numeric ID
            if len(df.columns) >= 2:
                first_vals = df.iloc[:3, 0].astype(str)
                if all(v.isdigit() for v in first_vals):
                    artist_col = df.columns[1]

        if not artist_col:
            with _geni_lock:
                item["status"] = "error"
                item["error"] = "No artist column found"
            _geni_broadcast({"type": "item_error", "item": _geni_item_dict(item)})
            return

        artists = df[artist_col].dropna().astype(str).str.strip().tolist()
        artists = [a for a in artists if a]  # drop blanks up front

        keys = _gather_genius_keys()

        with _geni_lock:
            item["total"] = len(artists)
            item["_contacts"] = []
            item["found"] = 0
            item["processed"] = 0
        _geni_broadcast({"type": "item_started", "item": _geni_item_dict(item)})

        if not keys:
            with _geni_lock:
                item["status"] = "error"
                item["error"] = "No Genius API key configured — add one in Settings."
            _geni_broadcast({"type": "item_error", "item": _geni_item_dict(item)})
            return

        n_keys = len(keys)
        per_key = (len(artists) + n_keys - 1) // n_keys if n_keys else 0  # ceil
        # Announce total artist count + how the run is divided across keys.
        _geni_broadcast({
            "type": "run_plan",
            "item_id": item["id"],
            "total": len(artists),
            "keys": n_keys,
            "per_key": per_key,
            "text": (f"{len(artists)} artists \u2192 {n_keys} Genius key"
                     f"{'s' if n_keys != 1 else ''}, ~{per_key} each"),
        })

        # ---- Work-stealing pool: one thread per key, shared artist queue ----
        # A shared queue (rather than fixed 250-row slices) splits work ~evenly
        # across keys AND auto-rebalances: a throttled key processes fewer while
        # healthy keys pick up the slack. Each key has its own 2 req/sec budget
        # (per-key limiter in genius.py), so N keys give ~N x throughput. A
        # persistently flagged key hands its artist to another key (capped
        # requeue) so nothing is lost. Works for any key count from 1 to 4+.
        from collections import deque
        pending = deque(range(len(artists)))
        requeues = {}
        MAX_REQUEUE = max(0, n_keys - 1)  # an artist may try every key once
        work_lock = _geni_threading.Lock()

        def _stopped():
            return bool(_geni_stop_flags.get(item["id"]))

        def _claim():
            with work_lock:
                return pending.popleft() if pending else None

        def _requeue(idx):
            with work_lock:
                requeues[idx] = requeues.get(idx, 0) + 1
                if requeues[idx] <= MAX_REQUEUE:
                    pending.append(idx)
                    return True
                return False

        def _record(idx, artist_name, socials):
            contact = {"artist": artist_name, "instagram": "", "facebook": "",
                       "match_confidence": "", "_idx": idx}
            has_social = False
            if socials:
                contact["instagram"] = socials.get("instagram", "")
                contact["facebook"] = socials.get("facebook", "")
                contact["match_confidence"] = socials.get("match_confidence", "")
                has_social = bool(contact["instagram"] or contact["facebook"])
            with _geni_lock:
                item["_contacts"].append(contact)
                item["processed"] = item.get("processed", 0) + 1
                if has_social:
                    item["found"] = item.get("found", 0) + 1
                processed, total = item["processed"], item["total"]
            _geni_broadcast({
                "type": "contact_done",
                "item_id": item["id"],
                "artist": artist_name,
                "socials": {
                    "instagram": contact["instagram"],
                    "facebook": contact["facebook"],
                    "match_confidence": contact["match_confidence"],
                },
                "processed": processed,
                "total": total,
            })

        def _key_worker(key, slot_no):
            while not _stopped():
                idx = _claim()
                if idx is None:
                    return
                artist_name = artists[idx]
                socials, gave_up = _genius_socials_resilient(
                    artist_name, key=key,
                    stop_check=_stopped,
                    on_cooldown=lambda attempt, sn=slot_no, an=artist_name: _geni_broadcast({
                        "type": "rate_limit_cooldown",
                        "item_id": item["id"],
                        "artist": an,
                        "slot": sn,
                        "attempt": attempt,
                        "max_attempts": GENI_MAX_RL_RETRIES,
                        "cooldown": GENI_RL_COOLDOWN,
                    }),
                )
                if gave_up and not _stopped():
                    # This key has been throttled past the whole backoff schedule
                    # — it won't recover soon. Hand the artist back for a healthy
                    # key and RETIRE this worker so a flagged key can't monopolize
                    # the queue. If every key has already tried it, record empty.
                    if _requeue(idx):
                        _geni_broadcast({
                            "type": "key_failover",
                            "item_id": item["id"],
                            "artist": artist_name,
                            "slot": slot_no,
                        })
                    else:
                        _record(idx, artist_name, None)
                    return
                _record(idx, artist_name, socials)

        # Hold the cross-pass lock for the whole Genius-consuming run.
        with genius_pass_lock:
            threads = []
            for slot_no, key in enumerate(keys, start=1):
                t = _geni_threading.Thread(
                    target=_key_worker, args=(key, slot_no), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

            # Drain any items still pending (e.g. all keys retired after being
            # throttled) so the run always completes with processed == total.
            if not _stopped():
                while True:
                    idx = _claim()
                    if idx is None:
                        break
                    _record(idx, artists[idx], None)

        stopped = _stopped()
        with _geni_lock:
            item["status"] = "stopped" if stopped else "done"
        _geni_broadcast({
            "type": "item_stopped" if stopped else "item_done",
            "item": _geni_item_dict(item),
        })

        # Auto-start next queued
        with _geni_lock:
            next_queued = [i for i in _geni_items if i["status"] == "queued"][:1]
        for ni in next_queued:
            _geni_stop_flags[ni["id"]] = False
            t = _geni_threading.Thread(target=_geni_worker, args=(ni,), daemon=True)
            _geni_active_threads[ni["id"]] = t
            t.start()

    except Exception as e:
        import traceback
        print(f"[genitractor] Error: {e}\n{traceback.format_exc()}", flush=True)
        with _geni_lock:
            item["status"] = "error"
            item["error"] = str(e)
        _geni_broadcast({"type": "item_error", "item": _geni_item_dict(item)})
    finally:
        _geni_active_threads.pop(item["id"], None)
        # Cleanup upload file
        try:
            Path(item["path"]).unlink(missing_ok=True)
        except Exception:
            pass


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
        f"version: v6.0.0",
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
