"""Stats API — lifetime metrics for dashboard widgets."""
from flask import Blueprint, jsonify
from flask_login import login_required, current_user

from app.database import Session, LifetimeStats

stats_bp = Blueprint("stats", __name__, url_prefix="/api/stats")


@stats_bp.route("/lifetime")
@login_required
def lifetime():
    """Return lifetime stats for the current user's dashboard widgets."""
    session = Session()
    try:
        stats = session.query(LifetimeStats).filter_by(user_id=current_user.id).first()
        if not stats:
            return jsonify({
                "total_processed": 0,
                "total_yield": 0,
                "emails_sent": 0,
            })

        # Yield = (total_keep + total_found) / total_processed * 100
        total = stats.total_processed or 1
        yield_pct = round(((stats.total_keep + stats.total_found) / total) * 100, 1)

        return jsonify({
            "total_processed": stats.total_processed,
            "total_yield": yield_pct,
            "emails_sent": stats.emails_sent,
        })
    finally:
        Session.remove()
