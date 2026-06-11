"""Drafter API — creates Gmail drafts from artist library data.

Uses Gmail API (OAuth2) to create one draft per artist with a valid email.
Template matches the existing Google Apps Script outreach format.
Runs entirely from the platform — no Google Sheets middleman.
"""
import os
import json
import time
import base64
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from queue import Queue, Full

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app import config
from app.database import Session, Artist

drafter_bp = Blueprint("drafter", __name__, url_prefix="/api/drafter")

# SSE subscribers for live progress
_drafter_subscribers = []
_drafter_lock = threading.Lock()
_drafter_running = False
_drafter_stop = False
_drafter_stats = {"created": 0, "skipped": 0, "total": 0, "status": "idle"}

# Gmail API credentials path
CREDS_PATH = config.BASE_DIR / "credentials.json"
TOKEN_PATH = config.BASE_DIR / "data" / "gmail_token.json"

# Email template config
SENDER_NAME = "Gavin Roy"
COMPANY = "Ignite The Label"
WEBSITE = "ignitethelabel.com"


def _broadcast(event):
    with _drafter_lock:
        dead = []
        for q in _drafter_subscribers:
            try:
                q.put_nowait(event)
            except Full:
                dead.append(q)
        for q in dead:
            try:
                _drafter_subscribers.remove(q)
            except ValueError:
                pass


def _get_gmail_service():
    """Build Gmail API service with stored OAuth credentials."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    SCOPES = ['https://www.googleapis.com/auth/gmail.compose']
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=9090, open_browser=True)

        TOKEN_PATH.parent.mkdir(exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def _build_draft_html(artist_name):
    """Build the HTML email body (same template as the Apps Script)."""
    return f'''<div style="margin:0;padding:0;line-height:1.15;font-family:'Google Sans',Roboto,Arial,sans-serif;font-size:11pt;">
Dear {artist_name} Management,<br>
<br>
I came across {artist_name}'s catalog and wanted to reach out directly. We work with artists and their teams on catalog acquisitions, and based on what's there, I think there's a conversation worth having.<br>
<br>
Would you be open to connecting for a quick call?<br>
<br>
Best,<br>
<br>
{SENDER_NAME}<br>
{COMPANY}<br>
<a href="https://{WEBSITE}" style="margin:0;padding:0;line-height:1.15;font-family:'Google Sans',Roboto,Arial,sans-serif;font-size:11pt;">{WEBSITE}</a>
</div>'''


def _build_draft_plain(artist_name):
    """Plain text fallback."""
    return f"""Dear {artist_name} Management,

I came across {artist_name}'s catalog and wanted to reach out directly. We work with artists and their teams on catalog acquisitions, and based on what's there, I think there's a conversation worth having.

Would you be open to connecting for a quick call?

Best,

{SENDER_NAME}
{COMPANY}
{WEBSITE}"""


def _create_gmail_draft(service, to_email, artist_name):
    """Create a single Gmail draft."""
    msg = MIMEMultipart('alternative')
    msg['To'] = to_email
    msg['Subject'] = artist_name

    plain = MIMEText(_build_draft_plain(artist_name), 'plain')
    html = MIMEText(_build_draft_html(artist_name), 'html')
    msg.attach(plain)
    msg.attach(html)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
    draft = service.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute()
    return draft


@drafter_bp.route("/status")
@login_required
def drafter_status():
    return jsonify(_drafter_stats)


@drafter_bp.route("/auth-check")
@login_required
def auth_check():
    """Check if Gmail API credentials are configured."""
    has_creds = CREDS_PATH.exists()
    has_token = TOKEN_PATH.exists()
    return jsonify({"has_credentials": has_creds, "has_token": has_token, "ready": has_creds})


@drafter_bp.route("/authorize", methods=["POST"])
@login_required
def authorize():
    """Trigger OAuth flow to get Gmail token."""
    try:
        service = _get_gmail_service()
        if service:
            return jsonify({"ok": True, "message": "Gmail authorized"})
        return jsonify({"error": "No credentials.json found"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@drafter_bp.route("/run", methods=["POST"])
@login_required
def run_drafter():
    """Create Gmail drafts for artists in the specified week/filter."""
    global _drafter_running, _drafter_stop

    if _drafter_running:
        return jsonify({"error": "Already running"}), 409

    data = request.get_json(silent=True) or {}
    batch_label = data.get("batch_label", "")
    status_filter = data.get("status_filter", "Not Sent")

    _drafter_stop = False
    t = threading.Thread(target=_drafter_worker, args=(current_user.id, batch_label, status_filter), daemon=True)
    t.start()

    return jsonify({"ok": True})


@drafter_bp.route("/stop", methods=["POST"])
@login_required
def stop_drafter():
    global _drafter_stop
    _drafter_stop = True
    return jsonify({"ok": True})


@drafter_bp.route("/stream")
@login_required
def drafter_stream():
    """SSE stream for live progress."""
    from flask import Response
    q = Queue(maxsize=200)
    with _drafter_lock:
        _drafter_subscribers.append(q)

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
            with _drafter_lock:
                try:
                    _drafter_subscribers.remove(q)
                except ValueError:
                    pass

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _drafter_worker(user_id, batch_label, status_filter):
    """Background worker: creates Gmail drafts for matching artists."""
    global _drafter_running, _drafter_stop, _drafter_stats

    _drafter_running = True
    _drafter_stats = {"created": 0, "skipped": 0, "total": 0, "status": "running"}
    _broadcast({"type": "started"})

    session = Session()
    try:
        service = _get_gmail_service()
        if not service:
            _broadcast({"type": "error", "message": "Gmail not authorized. Add credentials.json and authorize."})
            _drafter_stats["status"] = "error"
            return

        # Query artists
        q = session.query(Artist).filter_by(user_id=user_id)
        if batch_label:
            q = q.filter(Artist.batch_label == batch_label)
        if status_filter:
            q = q.filter(Artist.status == status_filter)

        artists = q.order_by(Artist.artist_name.asc()).all()
        _drafter_stats["total"] = len(artists)
        _broadcast({"type": "total", "count": len(artists)})

        for i, artist in enumerate(artists):
            if _drafter_stop:
                _broadcast({"type": "stopped"})
                _drafter_stats["status"] = "stopped"
                return

            if not artist.emails or not artist.emails.strip():
                _drafter_stats["skipped"] += 1
                _broadcast({"type": "skip", "artist": artist.artist_name, "reason": "no email"})
                continue

            try:
                emails = artist.emails.split(",")[0].strip()  # Use first email
                _create_gmail_draft(service, emails, artist.artist_name)
                _drafter_stats["created"] += 1
                _broadcast({"type": "drafted", "artist": artist.artist_name, "email": emails,
                            "processed": i + 1, "total": len(artists)})

                # Throttle: pause every 10 drafts
                if _drafter_stats["created"] % 10 == 0:
                    time.sleep(1.5)

            except Exception as e:
                _drafter_stats["skipped"] += 1
                _broadcast({"type": "error_artist", "artist": artist.artist_name, "error": str(e)})

        _drafter_stats["status"] = "done"
        _broadcast({"type": "done", "created": _drafter_stats["created"], "skipped": _drafter_stats["skipped"]})

    except Exception as e:
        _drafter_stats["status"] = "error"
        _broadcast({"type": "error", "message": str(e)})
    finally:
        _drafter_running = False
        Session.remove()
