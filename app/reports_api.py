"""Reports API — generates professional summary reports for presentation."""
import time
from datetime import datetime
from flask import Blueprint, Response
from flask_login import login_required, current_user

from app.database import Session, Artist, LifetimeStats

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@reports_bp.route("/summary")
@login_required
def summary_report():
    """Generate a professional HTML summary report for the boss."""
    session = Session()
    try:
        user_id = current_user.id
        from sqlalchemy import func

        total = session.query(func.count(Artist.id)).filter_by(user_id=user_id).scalar() or 0
        by_status = dict(session.query(Artist.status, func.count(Artist.id)).filter_by(user_id=user_id).group_by(Artist.status).all())
        by_momentum = dict(session.query(Artist.momentum, func.count(Artist.id)).filter_by(user_id=user_id).group_by(Artist.momentum).all())
        avg_listeners = session.query(func.avg(Artist.monthly_listeners)).filter_by(user_id=user_id).scalar() or 0

        # Top regions
        top_regions = session.query(Artist.region, func.count(Artist.id)).filter_by(user_id=user_id).group_by(Artist.region).order_by(func.count(Artist.id).desc()).limit(5).all()

        # Recent batches
        batches = session.query(Artist.batch_label, func.count(Artist.id)).filter_by(user_id=user_id).filter(Artist.batch_label != "").group_by(Artist.batch_label).order_by(Artist.batch_label.desc()).limit(5).all()

        # Lifetime stats
        stats = session.query(LifetimeStats).filter_by(user_id=user_id).first()

        now = datetime.now()
        report_date = now.strftime("%B %d, %Y")

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>IGNITE Scouting Report</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Inter',sans-serif;font-size:12px;color:#1a1a1a;background:#fff;padding:40px 60px;max-width:800px;margin:0 auto;line-height:1.5}}
.header{{border-bottom:2px solid #0c0e12;padding-bottom:16px;margin-bottom:24px}}
.header h1{{font-size:16px;font-weight:800;letter-spacing:.2em;color:#0c0e12}}
.header p{{font-size:9px;letter-spacing:.15em;color:#666;margin-top:4px}}
.date{{font-size:9px;color:#999;margin-top:2px}}
.section{{margin-bottom:24px}}
.section h2{{font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#89b0ae;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid #eee}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px}}
.stat-card{{background:#f8f9fa;border:1px solid #eee;border-radius:6px;padding:12px}}
.stat-card .val{{font-size:18px;font-weight:800;color:#0c0e12}}
.stat-card .lbl{{font-size:8px;letter-spacing:.1em;color:#666;text-transform:uppercase;margin-top:2px}}
table{{width:100%;border-collapse:collapse;font-size:10px;margin-top:8px}}
th{{text-align:left;font-size:8px;font-weight:700;letter-spacing:.08em;color:#666;text-transform:uppercase;padding:6px 8px;border-bottom:1px solid #ddd}}
td{{padding:5px 8px;border-bottom:1px solid #f0f0f0}}
.footer{{margin-top:32px;padding-top:12px;border-top:1px solid #eee;font-size:8px;color:#999;letter-spacing:.1em;text-align:center}}
@media print{{body{{padding:20px}}}}
</style></head><body>
<div class="header">
<h1>IGNITE THE LABEL</h1>
<p>VIRTUAL SCOUT · SCOUTING PIPELINE REPORT</p>
<p class="date">{report_date}</p>
</div>

<div class="section">
<h2>Pipeline Overview</h2>
<div class="grid">
<div class="stat-card"><div class="val">{total:,}</div><div class="lbl">Total Artists</div></div>
<div class="stat-card"><div class="val">{avg_listeners:,.0f}</div><div class="lbl">Avg Monthly Listeners</div></div>
<div class="stat-card"><div class="val">{by_status.get('Moving Forward', 0)}</div><div class="lbl">Moving Forward</div></div>
</div>
</div>

<div class="section">
<h2>Status Breakdown</h2>
<table>
<thead><tr><th>Status</th><th>Count</th><th>%</th></tr></thead>
<tbody>"""

        for status_name in ['Not Sent', 'Email Sent', 'Follow Up Sent', 'Moving Forward', 'Wrong Email']:
            count = by_status.get(status_name, 0)
            pct = (count / total * 100) if total > 0 else 0
            html += f"<tr><td>{status_name}</td><td>{count}</td><td>{pct:.1f}%</td></tr>\n"

        html += """</tbody></table></div>

<div class="section">
<h2>Momentum Distribution</h2>
<table>
<thead><tr><th>Momentum</th><th>Count</th><th>%</th></tr></thead>
<tbody>"""

        for mom in ['Growth', 'Steady', 'Slowing', 'Cooling', 'Explosive Growth']:
            count = by_momentum.get(mom, 0)
            pct = (count / total * 100) if total > 0 else 0
            if count > 0:
                html += f"<tr><td>{mom}</td><td>{count}</td><td>{pct:.1f}%</td></tr>\n"

        html += """</tbody></table></div>

<div class="section">
<h2>Top Regions</h2>
<table>
<thead><tr><th>Region</th><th>Artists</th></tr></thead>
<tbody>"""

        for region, count in top_regions:
            if region:
                html += f"<tr><td>{region}</td><td>{count}</td></tr>\n"

        html += """</tbody></table></div>"""

        if batches:
            html += """<div class="section">
<h2>Recent Batches</h2>
<table>
<thead><tr><th>Batch</th><th>Artists</th></tr></thead>
<tbody>"""
            for batch, count in batches:
                html += f"<tr><td>{batch}</td><td>{count}</td></tr>\n"
            html += "</tbody></table></div>"

        html += f"""
<div class="footer">
IGNITE THE LABEL · VIRTUAL SCOUT · Generated {report_date}
</div>
</body></html>"""

        return Response(html, mimetype="text/html")
    finally:
        Session.remove()
