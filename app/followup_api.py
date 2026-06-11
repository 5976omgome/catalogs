"""Follow Upper API — creates follow-up reply drafts for labeled Gmail threads.

Reads threads from Gmail labels like "Weeks/Week Of 05/10/Follow Ups",
extracts the artist name from the subject, and creates a reply draft
with the follow-up template. Skips threads that already have a draft.
"""
import json
import time
import base64
import threading
from email.mime.text import MIMEText
from queue import Queue, Full

from flask import Blueprint, request, jsonify, Response
from flask_login import login_required, current_user

from app import config

followup_bp = Blueprint("followup", __name__, url_prefix="/api/followup")

# SSE subscribers
_followup_subscribers = []
_followup_lock = threading.Lock()
_followup_running = False
_followup_stop = False
_followup_stats = {"created": 0, "skipped": 0, "total": 0, "status": "idle"}

# Week labels to scan
WEEK_LABELS = [
    "Weeks/Week Of 05/10",
    "Weeks/Week Of 05/17",
    "Weeks/Week Of 05/24",
    "Weeks/Week Of 05/31",
    "Weeks/Week Of 06/07",
]
FOLLOWUP_SUBLABEL = "Follow Ups"

SIGNATURE = """Best,
Gavin Roy
Ignite The Label
ignitethelabel.com"""


def _broadcast(event):
    with _followup_lock:
        dead = []
        for q in _followup_subscribers:
            try:
                q.put_nowait(event)
            except Full:
                dead.append(q)
        for q in dead:
            try:
                _followup_subscribers.remove(q)
            except ValueError:
                pass


def _get_gmail_service():
    """Reuse the same Gmail OAuth token as the Drafter."""
    from app.drafter_api import _get_gmail_service as get_svc
    return get_svc()


def _extract_artist_name(subject):
    """Extract artist name from email subject line."""
    import re
    clean = re.sub(r'^(re:|fwd?:|fw:)\s*', '', subject, flags=re.IGNORECASE).strip()
    parts = re.split(r'\s*[-|]\s*', clean)
    if len(parts) >= 2:
        generic = ["catalog", "inquiry", "ignite", "label", "music", "licensing", "deal"]
        first = parts[0].strip()
        last = parts[-1].strip()
        if not any(w in first.lower() for w in generic):
            return first
        if not any(w in last.lower() for w in generic):
            return last
    return clean


def _build_followup_body(artist_name):
    """Build the follow-up email text."""
    return f"""Hey,

I reached out a little while back regarding {artist_name}'s catalog but wanted to follow up in case it got buried. We work with artists and their teams on catalog licensing deals, and I think the music could be a strong fit for something we're currently developing.

Happy to keep it brief. Would you be open to a quick call?

{SIGNATURE}"""


@followup_bp.route("/status")
@login_required
def followup_status():
    return jsonify(_followup_stats)


@followup_bp.route("/labels")
@login_required
def list_labels():
    """List available Gmail labels for follow-up processing."""
    try:
        service = _get_gmail_service()
        if not service:
            return jsonify({"error": "Gmail not authorized"}), 400

        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])
        # Filter to only week/followup labels
        week_labels = [l for l in labels if 'Week' in l.get('name', '') and FOLLOWUP_SUBLABEL in l.get('name', '')]
        return jsonify({"labels": [{"id": l["id"], "name": l["name"]} for l in week_labels]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@followup_bp.route("/run", methods=["POST"])
@login_required
def run_followup():
    """Create follow-up reply drafts for all Follow Up labeled threads."""
    global _followup_running, _followup_stop

    if _followup_running:
        return jsonify({"error": "Already running"}), 409

    data = request.get_json(silent=True) or {}
    week_filter = data.get("week", "")  # Optional: specific week only

    _followup_stop = False
    t = threading.Thread(target=_followup_worker, args=(week_filter,), daemon=True)
    t.start()

    return jsonify({"ok": True})


@followup_bp.route("/stop", methods=["POST"])
@login_required
def stop_followup():
    global _followup_stop
    _followup_stop = True
    return jsonify({"ok": True})


@followup_bp.route("/stream")
@login_required
def followup_stream():
    """SSE stream for live progress."""
    q = Queue(maxsize=200)
    with _followup_lock:
        _followup_subscribers.append(q)

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
            with _followup_lock:
                try:
                    _followup_subscribers.remove(q)
                except ValueError:
                    pass

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _followup_worker(week_filter):
    """Background worker: scan Follow Ups labels and create reply drafts."""
    global _followup_running, _followup_stop, _followup_stats

    _followup_running = True
    _followup_stats = {"created": 0, "skipped": 0, "total": 0, "status": "running"}
    _broadcast({"type": "started"})

    try:
        service = _get_gmail_service()
        if not service:
            _broadcast({"type": "error", "message": "Gmail not authorized"})
            _followup_stats["status"] = "error"
            return

        # Get all labels
        results = service.users().labels().list(userId='me').execute()
        all_labels = {l['name']: l['id'] for l in results.get('labels', [])}

        # Get existing draft thread IDs to avoid duplicates
        drafts = service.users().drafts().list(userId='me').execute()
        existing_draft_threads = set()
        for d in drafts.get('drafts', []):
            try:
                draft_detail = service.users().drafts().get(userId='me', id=d['id']).execute()
                thread_id = draft_detail.get('message', {}).get('threadId')
                if thread_id:
                    existing_draft_threads.add(thread_id)
            except Exception:
                pass

        # Determine which weeks to process
        weeks_to_process = WEEK_LABELS
        if week_filter:
            weeks_to_process = [w for w in WEEK_LABELS if week_filter in w]

        total_threads = 0
        for week in weeks_to_process:
            full_label = f"{week}/{FOLLOWUP_SUBLABEL}"
            label_id = all_labels.get(full_label)
            if not label_id:
                _broadcast({"type": "sys", "text": f"Label not found: {full_label}", "cls": "warn"})
                continue

            # Get threads with this label
            threads_result = service.users().threads().list(userId='me', labelIds=[label_id]).execute()
            threads = threads_result.get('threads', [])
            total_threads += len(threads)

        _followup_stats["total"] = total_threads
        _broadcast({"type": "total", "count": total_threads})

        for week in weeks_to_process:
            if _followup_stop:
                break

            full_label = f"{week}/{FOLLOWUP_SUBLABEL}"
            label_id = all_labels.get(full_label)
            if not label_id:
                continue

            _broadcast({"type": "sys", "text": f"Processing: {full_label}", "cls": "info"})

            threads_result = service.users().threads().list(userId='me', labelIds=[label_id]).execute()
            threads = threads_result.get('threads', [])

            for thread_data in threads:
                if _followup_stop:
                    break

                thread_id = thread_data['id']

                # Skip if draft already exists for this thread
                if thread_id in existing_draft_threads:
                    _followup_stats["skipped"] += 1
                    _broadcast({"type": "skip", "reason": "draft exists"})
                    continue

                try:
                    # Get thread details
                    thread = service.users().threads().get(userId='me', id=thread_id).execute()
                    messages = thread.get('messages', [])
                    if not messages:
                        continue

                    # Extract artist name from subject
                    first_msg = messages[0]
                    headers = {h['name']: h['value'] for h in first_msg.get('payload', {}).get('headers', [])}
                    subject = headers.get('Subject', '')
                    artist_name = _extract_artist_name(subject)

                    # Get the last message to reply to
                    last_msg = messages[-1]
                    last_msg_id = last_msg['id']

                    # Build reply draft
                    body_text = _build_followup_body(artist_name)
                    reply_msg = MIMEText(body_text, 'plain')
                    reply_msg['Subject'] = f"Re: {subject}" if not subject.lower().startswith('re:') else subject
                    reply_msg['In-Reply-To'] = last_msg_id
                    reply_msg['References'] = last_msg_id

                    # Get the To address from the original
                    to_addr = headers.get('From', '') or headers.get('To', '')
                    reply_msg['To'] = to_addr

                    raw = base64.urlsafe_b64encode(reply_msg.as_bytes()).decode('utf-8')

                    service.users().drafts().create(userId='me', body={
                        'message': {'raw': raw, 'threadId': thread_id}
                    }).execute()

                    _followup_stats["created"] += 1
                    existing_draft_threads.add(thread_id)
                    _broadcast({"type": "drafted", "artist": artist_name, "week": week.split('/')[-1]})

                    time.sleep(0.3)

                except Exception as e:
                    _followup_stats["skipped"] += 1
                    _broadcast({"type": "error_artist", "artist": subject, "error": str(e)})

        _followup_stats["status"] = "done"
        _broadcast({"type": "done", "created": _followup_stats["created"], "skipped": _followup_stats["skipped"]})

    except Exception as e:
        _followup_stats["status"] = "error"
        _broadcast({"type": "error", "message": str(e)})
    finally:
        _followup_running = False
