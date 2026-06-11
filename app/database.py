"""SQLite database — models and initialization.

Uses SQLAlchemy ORM with a single-file SQLite database stored in the
project's data directory. Includes User model with bcrypt password hashing,
API keys with per-service slots, and lifetime stats for dashboard widgets.
"""
import os
import time
from pathlib import Path

import bcrypt
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

from app import config

# Database file lives in the project root data/ directory
DB_DIR = config.BASE_DIR / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "ignite.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

Session = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(128), default="")
    role = Column(String(32), default="viewer")  # admin, viewer
    timezone = Column(String(64), default="America/New_York")
    totp_secret = Column(String(64), default=None)  # 2FA secret (None = not enabled)
    totp_enabled = Column(Boolean, default=False)
    created_at = Column(Float, default=time.time)

    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            self.password_hash.encode("utf-8"),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "timezone": self.timezone,
        }


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    service = Column(String(32), nullable=False)  # genius, groq, gemini
    slot = Column(Integer, default=1)  # 1-4 for genius, 1 for others
    key_value = Column(Text, nullable=False)
    is_valid = Column(Boolean, default=None)
    last_validated = Column(Float, default=None)
    requests_today = Column(Integer, default=0)

    def masked(self) -> str:
        """Show only last 4 characters."""
        if len(self.key_value) <= 4:
            return "****"
        return "•" * 8 + self.key_value[-4:]


class Artist(Base):
    __tablename__ = "artists"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    artist_name = Column(String(255), nullable=False)
    chartmetric_id = Column(String(32), default="")
    country = Column(String(128), default="")
    region = Column(String(128), default="")
    continent = Column(String(64), default="")
    pronouns = Column(String(32), default="")
    solo_group = Column(String(32), default="")
    associated_labels = Column(Text, default="")
    label_category = Column(String(64), default="")
    genres = Column(Text, default="")
    moods = Column(Text, default="")
    activities = Column(Text, default="")
    career_stage = Column(String(32), default="")
    momentum = Column(String(32), default="")
    spotify_followers = Column(Integer, default=0)
    monthly_listeners = Column(Integer, default=0)
    instagram_followers = Column(Integer, default=0)
    instagram_engagement = Column(String(16), default="")
    spotify_link = Column(Text, default="")
    first_release = Column(String(32), default="")
    latest_release = Column(String(32), default="")
    # Genitact data
    emails = Column(Text, default="")
    instagram = Column(Text, default="")
    facebook = Column(Text, default="")
    # User workflow
    status = Column(String(32), default="Not Sent")
    batch_label = Column(String(64), default="")
    notes = Column(Text, default="")
    # Extra columns from CSV stored as JSON
    extra_data = Column(JSON, default=None)
    imported_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=None)

    def to_dict(self):
        return {
            "id": self.id,
            "artist_name": self.artist_name,
            "chartmetric_id": self.chartmetric_id or "",
            "country": self.country or "",
            "region": self.region or "",
            "continent": self.continent or "",
            "pronouns": self.pronouns or "",
            "solo_group": self.solo_group or "",
            "associated_labels": self.associated_labels or "",
            "label_category": self.label_category or "",
            "genres": self.genres or "",
            "moods": self.moods or "",
            "activities": self.activities or "",
            "career_stage": self.career_stage or "",
            "momentum": self.momentum or "",
            "spotify_followers": self.spotify_followers or 0,
            "monthly_listeners": self.monthly_listeners or 0,
            "instagram_followers": self.instagram_followers or 0,
            "instagram_engagement": self.instagram_engagement or "",
            "spotify_link": self.spotify_link or "",
            "first_release": self.first_release or "",
            "latest_release": self.latest_release or "",
            "emails": self.emails or "",
            "instagram": self.instagram or "",
            "facebook": self.facebook or "",
            "status": self.status or "Not Sent",
            "batch_label": self.batch_label or "",
            "notes": self.notes or "",
            "extra_data": self.extra_data,
            "imported_at": self.imported_at,
        }


class LifetimeStats(Base):
    __tablename__ = "lifetime_stats"

    user_id = Column(Integer, primary_key=True)
    total_processed = Column(Integer, default=0)
    total_keep = Column(Integer, default=0)
    total_found = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    updated_at = Column(Float, default=time.time)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_db():
    """Create all tables and ensure exactly one account: admin / admin.

    Reuses the existing primary user (lowest id) if present so any imported
    artists/stats stay attached, renames it to 'admin', always resets the
    password to 'admin', clears 2FA, and removes any other accounts.
    Idempotent — safe on both a fresh and an existing database.
    """
    Base.metadata.create_all(engine)
    session = Session()
    try:
        admin = session.query(User).filter_by(email="admin").first()
        if not admin:
            # Reuse the original primary account so its data stays attached
            admin = session.query(User).order_by(User.id).first()
            if admin:
                admin.email = "admin"
                admin.name = "Admin"
                admin.role = "admin"
            else:
                admin = User(
                    email="admin",
                    name="Admin",
                    role="admin",
                    timezone="America/New_York",
                )
                session.add(admin)
                session.flush()  # assign id

        # Always guarantee the credentials work and 2FA can't block login
        admin.email = "admin"
        admin.role = "admin"
        admin.set_password("admin")
        admin.totp_enabled = False
        admin.totp_secret = None
        session.flush()

        admin_id = admin.id

        # Ensure lifetime stats row exists for this account
        if not session.query(LifetimeStats).filter_by(user_id=admin_id).first():
            session.add(LifetimeStats(user_id=admin_id))

        # Keep exactly one account
        session.query(User).filter(User.id != admin_id).delete(
            synchronize_session=False
        )

        session.commit()
        print("[db] Single account ready — login: admin / admin", flush=True)
    except Exception as e:
        session.rollback()
        print(f"[db] Init error: {e}", flush=True)
    finally:
        Session.remove()
