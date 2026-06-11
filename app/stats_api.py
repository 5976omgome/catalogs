"""Stats API — real-time metrics from the Artists library for dashboard."""
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func

from app.database import Session, Artist

stats_bp = Blueprint("stats", __name__, url_prefix="/api/stats")


@stats_bp.route("/lifetime")
@login_required
def lifetime():
    """Dashboard widgets — computed from the actual Artists table."""
    session = Session()
    try:
        uid = current_user.id
        total = session.query(func.count(Artist.id)).filter_by(user_id=uid).scalar() or 0

        # Emails sent = artists with status "Email Sent" or "Follow Up Sent" or "Moving Forward"
        sent_statuses = ['Email Sent', 'Follow Up Sent', 'Moving Forward']
        emails_sent = session.query(func.count(Artist.id)).filter(
            Artist.user_id == uid, Artist.status.in_(sent_statuses)
        ).scalar() or 0

        # Yield = emails_sent / total * 100
        yield_pct = round((emails_sent / max(total, 1)) * 100, 1)

        # Pipeline breakdown
        by_status = dict(session.query(Artist.status, func.count(Artist.id)).filter_by(
            user_id=uid).group_by(Artist.status).all())

        # Batches count
        batch_count = session.query(func.count(func.distinct(Artist.batch_label))).filter(
            Artist.user_id == uid, Artist.batch_label != ""
        ).scalar() or 0

        return jsonify({
            "total_processed": total,
            "total_yield": yield_pct,
            "emails_sent": emails_sent,
            "batches": batch_count,
            "moving_forward": by_status.get("Moving Forward", 0),
            "not_sent": by_status.get("Not Sent", 0),
        })
    finally:
        Session.remove()
