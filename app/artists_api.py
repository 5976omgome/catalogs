"""Artists API — import CSV, list/filter/sort, update status, batch labels."""
import csv
import io
import time
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.database import Session, Artist

artists_bp = Blueprint("artists", __name__, url_prefix="/api/artists")

# Column mapping: Chartmetric CSV header → Artist model field
_COL_MAP = {
    "chartmetric id": "chartmetric_id",
    "artist": "artist_name",
    "artist name": "artist_name",
    "country": "country",
    "region": "region",
    "continent": "continent",
    "pronouns": "pronouns",
    "solo/group": "solo_group",
    "associated labels": "associated_labels",
    "label category": "label_category",
    "genres": "genres",
    "moods": "moods",
    "activities": "activities",
    "career stage": "career_stage",
    "recent momentum": "momentum",
    "spotify followers": "spotify_followers",
    "spotify monthly listeners": "monthly_listeners",
    "instagram followers": "instagram_followers",
    "instagram engagement rate": "instagram_engagement",
    "spotify links": "spotify_link",
    "first release date": "first_release",
    "latest release date": "latest_release",
}

_INT_FIELDS = {"spotify_followers", "monthly_listeners", "instagram_followers"}


@artists_bp.route("/import", methods=["POST"])
@login_required
def import_csv():
    """Import a Chartmetric CSV into the artist library."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No filename"}), 400

    batch_label = request.form.get("batch_label", "").strip()

    try:
        content = f.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content), delimiter="\t" if f.filename.endswith(".tsv") else ",")
    except Exception as e:
        return jsonify({"error": f"Failed to parse CSV: {e}"}), 400

    session = Session()
    imported = 0
    skipped = 0

    try:
        for row in reader:
            mapped = {}
            extra = {}

            for col, val in row.items():
                if not col:
                    continue
                key = col.strip().lower()
                field = _COL_MAP.get(key)
                if field:
                    if field in _INT_FIELDS:
                        try:
                            mapped[field] = int(str(val).replace(",", "").strip()) if val else 0
                        except (ValueError, TypeError):
                            mapped[field] = 0
                    else:
                        mapped[field] = str(val).strip() if val else ""
                else:
                    extra[col.strip()] = str(val).strip() if val else ""

            artist_name = mapped.get("artist_name", "").strip()
            if not artist_name:
                skipped += 1
                continue

            artist = Artist(
                user_id=current_user.id,
                artist_name=artist_name,
                chartmetric_id=mapped.get("chartmetric_id", ""),
                country=mapped.get("country", ""),
                region=mapped.get("region", ""),
                continent=mapped.get("continent", ""),
                pronouns=mapped.get("pronouns", ""),
                solo_group=mapped.get("solo_group", ""),
                associated_labels=mapped.get("associated_labels", ""),
                label_category=mapped.get("label_category", ""),
                genres=mapped.get("genres", ""),
                moods=mapped.get("moods", ""),
                activities=mapped.get("activities", ""),
                career_stage=mapped.get("career_stage", ""),
                momentum=mapped.get("momentum", ""),
                spotify_followers=mapped.get("spotify_followers", 0),
                monthly_listeners=mapped.get("monthly_listeners", 0),
                instagram_followers=mapped.get("instagram_followers", 0),
                instagram_engagement=mapped.get("instagram_engagement", ""),
                spotify_link=mapped.get("spotify_link", ""),
                first_release=mapped.get("first_release", ""),
                latest_release=mapped.get("latest_release", ""),
                status="Not Sent",
                batch_label=batch_label,
                extra_data=extra if extra else None,
                imported_at=time.time(),
            )
            session.add(artist)
            imported += 1

        session.commit()
        return jsonify({"ok": True, "imported": imported, "skipped": skipped})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        Session.remove()


@artists_bp.route("/list")
@login_required
def list_artists():
    """List artists with filtering, sorting, pagination."""
    session = Session()
    try:
        q = session.query(Artist).filter_by(user_id=current_user.id)

        # Filters
        momentum = request.args.get("momentum")
        if momentum:
            q = q.filter(Artist.momentum == momentum)

        status = request.args.get("status")
        if status:
            q = q.filter(Artist.status == status)

        batch = request.args.get("batch_label")
        if batch:
            q = q.filter(Artist.batch_label == batch)

        region = request.args.get("region")
        if region:
            q = q.filter(Artist.region == region)

        min_listeners = request.args.get("min_listeners", type=int)
        if min_listeners is not None:
            q = q.filter(Artist.monthly_listeners >= min_listeners)

        max_listeners = request.args.get("max_listeners", type=int)
        if max_listeners is not None:
            q = q.filter(Artist.monthly_listeners <= max_listeners)

        search = request.args.get("search", "").strip()
        if search:
            q = q.filter(Artist.artist_name.ilike(f"%{search}%"))

        # Sort
        sort_by = request.args.get("sort", "imported_at")
        sort_dir = request.args.get("dir", "desc")
        col = getattr(Artist, sort_by, Artist.imported_at)
        q = q.order_by(col.desc() if sort_dir == "desc" else col.asc())

        # Count total (for UI)
        total = q.count()

        # Pagination
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 100, type=int)
        per_page = min(per_page, 500)
        artists = q.offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "artists": [a.to_dict() for a in artists],
            "total": total,
            "page": page,
            "per_page": per_page,
        })
    finally:
        Session.remove()


@artists_bp.route("/update/<int:artist_id>", methods=["PATCH"])
@login_required
def update_artist(artist_id):
    """Update an artist's status, batch_label, or notes."""
    session = Session()
    try:
        artist = session.query(Artist).filter_by(id=artist_id, user_id=current_user.id).first()
        if not artist:
            return jsonify({"error": "Not found"}), 404

        data = request.get_json(silent=True) or {}
        if "status" in data:
            artist.status = data["status"]
        if "batch_label" in data:
            artist.batch_label = data["batch_label"]
        if "notes" in data:
            artist.notes = data["notes"]
        if "emails" in data:
            artist.emails = data["emails"]

        artist.updated_at = time.time()
        session.commit()
        return jsonify({"ok": True, "artist": artist.to_dict()})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        Session.remove()


@artists_bp.route("/batch-update", methods=["POST"])
@login_required
def batch_update():
    """Batch update status or batch_label for multiple artists."""
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"error": "No artist IDs provided"}), 400

    session = Session()
    try:
        artists = session.query(Artist).filter(
            Artist.id.in_(ids), Artist.user_id == current_user.id
        ).all()

        for a in artists:
            if "status" in data:
                a.status = data["status"]
            if "batch_label" in data:
                a.batch_label = data["batch_label"]
            a.updated_at = time.time()

        session.commit()
        return jsonify({"ok": True, "updated": len(artists)})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        Session.remove()


@artists_bp.route("/export")
@login_required
def export_artists():
    """Export filtered artists as CSV."""
    session = Session()
    try:
        q = session.query(Artist).filter_by(user_id=current_user.id)

        # Apply same filters as list
        momentum = request.args.get("momentum")
        if momentum:
            q = q.filter(Artist.momentum == momentum)
        status = request.args.get("status")
        if status:
            q = q.filter(Artist.status == status)
        batch = request.args.get("batch_label")
        if batch:
            q = q.filter(Artist.batch_label == batch)

        artists = q.order_by(Artist.imported_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        headers = ["Artist Name", "Status", "Batch", "Monthly Listeners", "Momentum",
                   "Region", "Genres", "Associated Labels", "Instagram", "Emails",
                   "Career Stage", "Country", "Spotify Link"]
        writer.writerow(headers)

        for a in artists:
            writer.writerow([
                a.artist_name, a.status, a.batch_label, a.monthly_listeners,
                a.momentum, a.region, a.genres, a.associated_labels,
                a.instagram, a.emails, a.career_stage, a.country, a.spotify_link,
            ])

        from flask import Response
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=Artists_Export.csv"})
    finally:
        Session.remove()


@artists_bp.route("/stats")
@login_required
def artist_stats():
    """Quick stats for filters (unique values for momentum, regions, batches)."""
    session = Session()
    try:
        from sqlalchemy import func, distinct
        user_id = current_user.id

        total = session.query(func.count(Artist.id)).filter_by(user_id=user_id).scalar() or 0
        momentums = [r[0] for r in session.query(distinct(Artist.momentum)).filter_by(user_id=user_id).all() if r[0]]
        regions = [r[0] for r in session.query(distinct(Artist.region)).filter_by(user_id=user_id).all() if r[0]]
        batches = [r[0] for r in session.query(distinct(Artist.batch_label)).filter_by(user_id=user_id).all() if r[0]]
        statuses = [r[0] for r in session.query(distinct(Artist.status)).filter_by(user_id=user_id).all() if r[0]]

        return jsonify({
            "total": total,
            "momentums": sorted(momentums),
            "regions": sorted(regions),
            "batches": sorted(batches),
            "statuses": sorted(statuses),
        })
    finally:
        Session.remove()


@artists_bp.route("/delete", methods=["POST"])
@login_required
def delete_artists():
    """Delete artists by IDs."""
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"error": "No IDs"}), 400

    session = Session()
    try:
        deleted = session.query(Artist).filter(
            Artist.id.in_(ids), Artist.user_id == current_user.id
        ).delete(synchronize_session=False)
        session.commit()
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        Session.remove()
