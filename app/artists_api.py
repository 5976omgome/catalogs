"""Artists API — import CSV, list/filter/sort, update status, batch labels."""
import csv
import io
import re
import time
from flask import Blueprint, request, jsonify, Response
from flask_login import login_required, current_user

from app.database import Session, Artist

artists_bp = Blueprint("artists", __name__, url_prefix="/api/artists")

# Column mapping: various CSV header names → Artist model field
# Handles both Chartmetric exports AND the user's custom scout sheets
_COL_MAP = {
    # Artist name
    "artist": "artist_name", "artist name": "artist_name", "name": "artist_name",
    # Type (License/Buyout/A&R)
    "type": "solo_group",
    # Emails
    "emails": "emails", "email": "emails", "contact": "emails",
    # Instagram
    "instagram": "instagram", "ig": "instagram",
    # Spotify
    "spotify": "spotify_link", "spotify links": "spotify_link", "spotify link": "spotify_link",
    # Monthly listeners
    "monthly": "monthly_listeners", "monthly listeners": "monthly_listeners",
    "spotify monthly listeners": "monthly_listeners",
    # Momentum / Growth
    "growth": "momentum", "recent momentum": "momentum", "momentum": "momentum",
    # Status
    "status": "status",
    # Labels
    "label info": "associated_labels", "associated labels": "associated_labels",
    "labels": "associated_labels", "label category": "label_category",
    # Region
    "region": "region",
    # Genre
    "genre/scene": "genres", "genres": "genres", "genre": "genres",
    # Country
    "country": "country",
    # Chartmetric fields
    "chartmetric id": "chartmetric_id",
    "continent": "continent",
    "pronouns": "pronouns",
    "solo/group": "pronouns",  # reuse if "Type" not present
    "moods": "moods",
    "activities": "activities",
    "career stage": "career_stage",
    "spotify followers": "spotify_followers",
    "instagram followers": "instagram_followers",
    "instagram engagement rate": "instagram_engagement",
    "first release date": "first_release",
    "latest release date": "latest_release",
    # Facebook
    "facebook": "facebook",
}

_INT_FIELDS = {"spotify_followers", "monthly_listeners", "instagram_followers"}

# Email regex — extracts only valid email addresses from any surrounding text
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

# Momentum sort order for custom ranking
_MOMENTUM_ORDER = {'Explosive Growth': 0, 'Growth': 1, 'Steady': 2, 'Slowing': 3, 'Cooling': 4}


def _extract_emails(raw):
    """Extract only raw email addresses from text. Strips all labels/prefixes."""
    if not raw or not raw.strip():
        return ""
    # Check for "nothing" values
    cleaned = raw.strip().strip('"').strip()
    if cleaned in ('', '-', '--', 'N/A', 'n/a', 'none', 'None', ' '):
        return ""
    # Find all email patterns
    emails = _EMAIL_RE.findall(cleaned)
    return ", ".join(emails) if emails else ""


def _clean_instagram(raw):
    """Extract just the handle from Instagram URLs or raw text."""
    if not raw or not raw.strip():
        return ""
    val = raw.strip().strip('"').strip()
    if val in ('', '-', '--', ' '):
        return ""
    # Strip URL prefix
    val = re.sub(r'https?://(www\.)?instagram\.com/', '', val)
    val = val.rstrip('/').split('?')[0]
    if not val or val == '-':
        return ""
    return val


# Search column date pattern: MM/DD/YY at the start
_DATE_RE = re.compile(r'^(\d{2}/\d{2}/\d{2})')


def _parse_search_column(val):
    """Parse the Search column: extract date + characteristics.
    
    The Search column contains:
    - First line: date like "05/27/26"
    - Remaining lines: bullet-point notes about the batch
    
    Returns (date_str, characteristics_str)
    """
    if not val or not val.strip():
        return "", ""
    
    lines = val.strip().split("\n")
    date_str = ""
    chars = []
    
    for i, line in enumerate(lines):
        line = line.strip()
        if i == 0:
            m = _DATE_RE.match(line)
            if m:
                date_str = m.group(1)
                # If there's more text on the date line, keep it
                rest = line[m.end():].strip()
                if rest:
                    chars.append(rest)
            else:
                chars.append(line)
        elif line and line != "-":
            chars.append(line)
    
    characteristics = "\n".join(chars).strip()
    return date_str, characteristics


@artists_bp.route("/import", methods=["POST"])
@login_required
def import_csv():
    """Import a CSV into the artist library.
    
    Handles:
    - Tab-separated and comma-separated files
    - "Search" column with date + characteristics
    - Various column name formats (Chartmetric, custom scout sheets)
    - Emails, Instagram, Spotify columns
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No filename"}), 400

    batch_label = request.form.get("batch_label", "").strip()

    try:
        content = f.read().decode("utf-8-sig")
        # Detect delimiter
        first_line = content.split("\n")[0]
        delimiter = "\t" if "\t" in first_line else ","
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    except Exception as e:
        return jsonify({"error": f"Failed to parse CSV: {e}"}), 400

    session = Session()
    imported = 0
    skipped = 0
    current_search_date = ""
    current_characteristics = ""

    try:
        for row in reader:
            mapped = {}
            extra = {}
            search_val = ""

            for col, val in row.items():
                if not col:
                    continue
                key = col.strip().lower()
                
                # Handle Search column specially
                if key == "search":
                    search_val = (val or "").strip()
                    continue
                
                field = _COL_MAP.get(key)
                if field:
                    if field in _INT_FIELDS:
                        try:
                            cleaned = str(val or "").replace(",", "").replace(" ", "").strip()
                            mapped[field] = int(cleaned) if cleaned and cleaned.isdigit() else 0
                        except (ValueError, TypeError):
                            mapped[field] = 0
                    else:
                        mapped[field] = str(val).strip() if val else ""
                else:
                    if val and str(val).strip() and str(val).strip() != "-":
                        extra[col.strip()] = str(val).strip()

            # Parse Search column for date + characteristics
            if search_val:
                date_str, chars = _parse_search_column(search_val)
                if date_str:
                    current_search_date = f"Week Of {date_str}"
                if chars:
                    current_characteristics = chars

            artist_name = mapped.get("artist_name", "").strip()
            if not artist_name or artist_name == "-":
                skipped += 1
                continue

            # Dedupe: skip if artist already exists for this user (prevents double outreach)
            existing = session.query(Artist).filter(
                Artist.user_id == current_user.id,
                Artist.artist_name == artist_name
            ).first()
            if existing:
                skipped += 1
                continue

            # Determine the batch/week label
            week_label = batch_label or current_search_date

            # Clean up emails — extract only raw email addresses
            raw_emails = _extract_emails(mapped.get("emails", ""))

            # Clean Instagram
            raw_ig = _clean_instagram(mapped.get("instagram", ""))

            # Default momentum: if empty or monthly=0 with no growth data, set to Steady
            momentum_val = mapped.get("momentum", "").strip()
            if not momentum_val:
                momentum_val = "Steady"

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
                momentum=momentum_val,
                spotify_followers=mapped.get("spotify_followers", 0),
                monthly_listeners=mapped.get("monthly_listeners", 0),
                instagram_followers=mapped.get("instagram_followers", 0),
                instagram_engagement=mapped.get("instagram_engagement", ""),
                spotify_link=mapped.get("spotify_link", ""),
                first_release=mapped.get("first_release", ""),
                latest_release=mapped.get("latest_release", ""),
                emails=raw_emails,
                instagram=raw_ig,
                facebook=mapped.get("facebook", ""),
                status=mapped.get("status", "") or "Not Sent",
                batch_label=week_label,
                notes=current_characteristics,
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

        # Sort — custom momentum order, otherwise standard column sort
        sort_by = request.args.get("sort", "imported_at")
        sort_dir = request.args.get("dir", "desc")

        if sort_by == "momentum":
            # Custom order: Explosive Growth=0, Growth=1, Steady=2, Slowing=3, Cooling=4
            from sqlalchemy import case
            momentum_order = case(
                (Artist.momentum == "Explosive Growth", 0),
                (Artist.momentum == "Growth", 1),
                (Artist.momentum == "Steady", 2),
                (Artist.momentum == "Slowing", 3),
                (Artist.momentum == "Cooling", 4),
                else_=2  # default to Steady position
            )
            if sort_dir == "desc":
                # "descending" = highest value first = Explosive Growth at top
                q = q.order_by(momentum_order.asc(), Artist.artist_name.asc())
            else:
                q = q.order_by(momentum_order.desc(), Artist.artist_name.asc())
        else:
            col = getattr(Artist, sort_by, Artist.imported_at)
            if sort_dir == "desc":
                q = q.order_by(col.desc(), Artist.artist_name.asc())
            else:
                q = q.order_by(col.asc(), Artist.artist_name.asc())

        total = q.count()
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 100, type=int), 500)
        artists = q.offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "artists": [a.to_dict() for a in artists],
            "total": total, "page": page, "per_page": per_page,
        })
    finally:
        Session.remove()


@artists_bp.route("/update/<int:artist_id>", methods=["PATCH"])
@login_required
def update_artist(artist_id):
    """Update an artist's status, batch_label, notes, or emails."""
    session = Session()
    try:
        artist = session.query(Artist).filter_by(id=artist_id, user_id=current_user.id).first()
        if not artist:
            return jsonify({"error": "Not found"}), 404

        data = request.get_json(silent=True) or {}
        for field in ("status", "batch_label", "notes", "emails", "instagram", "facebook", "solo_group"):
            if field in data:
                setattr(artist, field, data[field])
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
        return jsonify({"error": "No IDs"}), 400

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
    """Export filtered artists as CSV. Supports single-column export."""
    session = Session()
    try:
        q = session.query(Artist).filter_by(user_id=current_user.id)

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

        artists = q.order_by(Artist.imported_at.desc()).all()

        # Page-only export (just 100 rows from a specific page)
        page_only = request.args.get("page_only")
        if page_only:
            page_num = request.args.get("page", 1, type=int)
            per_page = request.args.get("per_page", 100, type=int)
            artists = artists[(page_num-1)*per_page : page_num*per_page]

        # Single column export
        column = request.args.get("column")
        if column:
            valid_cols = {
                "artist_name", "emails", "instagram", "facebook", "spotify_link",
                "monthly_listeners", "momentum", "region", "genres",
                "associated_labels", "status", "batch_label", "country",
                "career_stage", "solo_group", "notes",
            }
            if column not in valid_cols:
                return jsonify({"error": f"Invalid column: {column}"}), 400

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([column])
            for a in artists:
                val = getattr(a, column, "") or ""
                if val:
                    writer.writerow([val])
            output.seek(0)
            return Response(output.getvalue(), mimetype="text/csv",
                            headers={"Content-Disposition": f"attachment; filename={column}_export.csv"})

        # Full export
        output = io.StringIO()
        writer = csv.writer(output)
        headers = ["Artist Name", "Type", "Emails", "Instagram", "Spotify",
                   "Monthly", "Momentum", "Status", "Labels", "Region",
                   "Genre/Scene", "Week", "Notes"]
        writer.writerow(headers)

        for a in artists:
            writer.writerow([
                a.artist_name, a.solo_group, a.emails, a.instagram,
                a.spotify_link, a.monthly_listeners, a.momentum,
                a.status, a.associated_labels, a.region,
                a.genres, a.batch_label, a.notes,
            ])

        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=Artists_Export.csv"})
    finally:
        Session.remove()


@artists_bp.route("/export-column/<column>")
@login_required
def export_single_column(column):
    """Export a single column from all artists as CSV."""
    valid_cols = {
        "artist_name": "Artist Name", "emails": "Emails",
        "instagram": "Instagram", "facebook": "Facebook",
        "spotify_link": "Spotify", "monthly_listeners": "Monthly Listeners",
        "momentum": "Momentum", "region": "Region", "genres": "Genres",
        "associated_labels": "Labels", "status": "Status",
        "batch_label": "Week", "country": "Country",
        "career_stage": "Career Stage", "solo_group": "Type", "notes": "Notes",
    }
    if column not in valid_cols:
        return jsonify({"error": f"Invalid column"}), 400

    session = Session()
    try:
        artists = session.query(Artist).filter_by(user_id=current_user.id).order_by(Artist.imported_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([valid_cols[column]])
        for a in artists:
            val = getattr(a, column, "") or ""
            if str(val).strip():
                writer.writerow([val])
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={column}_export.csv"})
    finally:
        Session.remove()


@artists_bp.route("/stats")
@login_required
def artist_stats():
    """Quick stats for filters."""
    session = Session()
    try:
        from sqlalchemy import func, distinct
        uid = current_user.id
        total = session.query(func.count(Artist.id)).filter_by(user_id=uid).scalar() or 0
        momentums = [r[0] for r in session.query(distinct(Artist.momentum)).filter_by(user_id=uid).all() if r[0]]
        regions = [r[0] for r in session.query(distinct(Artist.region)).filter_by(user_id=uid).all() if r[0]]
        batches = [r[0] for r in session.query(distinct(Artist.batch_label)).filter_by(user_id=uid).all() if r[0]]
        statuses = [r[0] for r in session.query(distinct(Artist.status)).filter_by(user_id=uid).all() if r[0]]
        return jsonify({"total": total, "momentums": sorted(momentums), "regions": sorted(regions), "batches": sorted(batches), "statuses": sorted(statuses)})
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



@artists_bp.route("/delete-batch", methods=["POST"])
@login_required
def delete_batch():
    """Delete all artists in a specific week/batch group."""
    data = request.get_json(silent=True) or {}
    batch_label = data.get("batch_label", "").strip()
    if not batch_label:
        return jsonify({"error": "No batch_label provided"}), 400
    session = Session()
    try:
        deleted = session.query(Artist).filter(
            Artist.user_id == current_user.id,
            Artist.batch_label == batch_label
        ).delete(synchronize_session=False)
        session.commit()
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        Session.remove()



@artists_bp.route("/dedupe", methods=["POST"])
@login_required
def dedupe_artists():
    """Remove duplicate artists. Keeps the oldest entry (lowest id), deletes copies.
    
    Matches by exact artist_name (case-sensitive). Returns count of removed dupes.
    """
    session = Session()
    try:
        from sqlalchemy import func
        uid = current_user.id

        # Find artist names that appear more than once
        dupes = session.query(Artist.artist_name, func.count(Artist.id).label('cnt')) \
            .filter_by(user_id=uid) \
            .group_by(Artist.artist_name) \
            .having(func.count(Artist.id) > 1) \
            .all()

        removed = 0
        for name, cnt in dupes:
            # Get all entries for this name, ordered by id (oldest first)
            entries = session.query(Artist).filter_by(
                user_id=uid, artist_name=name
            ).order_by(Artist.id.asc()).all()

            # Keep the first (oldest), delete the rest
            for entry in entries[1:]:
                session.delete(entry)
                removed += 1

        session.commit()
        return jsonify({"ok": True, "removed": removed, "dupes_found": len(dupes)})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        Session.remove()



@artists_bp.route("/crosscheck", methods=["POST"])
@login_required
def crosscheck_artists():
    """Temporary, read-only duplicate scan against the library.

    Upload a table (.csv / .tsv). For each row we compare the artist name to
    (a) every artist already in the user's library and (b) earlier rows in the
    SAME uploaded file. Nothing is saved, modified, or deleted — we just return
    the original table verbatim plus one extra flag column, and a summary the
    UI can show.

    Matching uses the same normaliser as Genius name-matching: case-insensitive,
    diacritic-folded, punctuation-stripped, leading-"the" removed — so
    "Beyoncé", "beyonce" and "The Beyonce " all collapse to one key.
    """
    import pandas as pd
    from app.sources.genius import normalize_name

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file uploaded"}), 400

    raw = f.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    # Delimiter sniff: honour .tsv, else pick whichever is more common in the head.
    sample = text[:5000]
    sep = "\t" if (f.filename.lower().endswith(".tsv") or sample.count("\t") > sample.count(",")) else ","

    try:
        df = pd.read_csv(
            io.StringIO(text), dtype=str, keep_default_na=False, na_filter=False, sep=sep
        )
    except Exception as e:
        return jsonify({"error": f"Could not parse file: {e}"}), 400

    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    headers = [str(h) for h in df.columns]
    if not headers:
        return jsonify({"error": "File has no columns."}), 400

    # Locate the artist-name column.
    artist_idx = None
    for i, h in enumerate(headers):
        if h.strip().lower() in ("artist", "artist name", "artist_name", "name", "performer"):
            artist_idx = i
            break
    if artist_idx is None:
        return jsonify({
            "error": "No artist column found. Expected a header named "
                     "'Artist', 'Artist Name', or 'Name'.",
            "headers_seen": headers,
        }), 400

    # Build library lookup: normalized name -> (display name, week label).
    session = Session()
    try:
        lib = session.query(Artist.artist_name, Artist.batch_label) \
            .filter_by(user_id=current_user.id).all()
    finally:
        Session.remove()

    lib_map = {}
    for nm, batch in lib:
        norm = normalize_name(nm or "")
        if norm and norm not in lib_map:
            lib_map[norm] = (nm or "", batch or "")

    # Pick a non-colliding header for the flag column.
    flag_col = "Duplicate?"
    existing = {h.strip().lower() for h in headers}
    if flag_col.lower() in existing:
        flag_col, n = "Duplicate Check", 2
        while flag_col.lower() in existing:
            flag_col = f"Duplicate Check {n}"
            n += 1

    out_headers = headers + [flag_col]
    out_rows = []
    seen_in_file = {}  # normalized name -> first row's display name
    lib_dupes = file_dupes = flagged = 0

    for rec in df.values.tolist():
        rec = ["" if v is None else str(v) for v in rec]
        if len(rec) < len(headers):
            rec += [""] * (len(headers) - len(rec))
        elif len(rec) > len(headers):
            rec = rec[:len(headers)]

        raw_name = rec[artist_idx].strip()
        norm = normalize_name(raw_name)

        notes = []
        if norm:
            if norm in lib_map:
                disp, wk = lib_map[norm]
                notes.append(f'DUPLICATE (library) — "{disp}"' + (f" · {wk}" if wk else ""))
                lib_dupes += 1
            if norm in seen_in_file:
                notes.append(f'DUPLICATE (in file) — repeats "{seen_in_file[norm]}"')
                file_dupes += 1
            else:
                seen_in_file[norm] = raw_name

        flag_val = "; ".join(notes)
        if flag_val:
            flagged += 1
        out_rows.append(rec + [flag_val])

    stem = re.sub(r"\.(csv|tsv)$", "", f.filename, flags=re.I)
    return jsonify({
        "ok": True,
        "headers": out_headers,
        "rows": out_rows,
        "flag_col": flag_col,
        "artist_column": headers[artist_idx],
        "summary": {
            "total": len(out_rows),
            "library_dupes": lib_dupes,
            "file_dupes": file_dupes,
            "flagged": flagged,
            "clean": len(out_rows) - flagged,
            "library_size": len(lib_map),
        },
        "filename": f"{stem}_crosschecked.csv",
    })
