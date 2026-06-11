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
    """Create all tables and seed user accounts if not present."""
    Base.metadata.create_all(engine)
    session = Session()
    try:
        # Seed admin user
        admin = session.query(User).filter_by(email="gavin.roy07@ignitethelabel.com").first()
        if not admin:
            admin = User(
                email="gavin.roy07@ignitethelabel.com",
                name="Gavin Roy",
                role="admin",
                timezone="America/New_York",
            )
            admin.set_password("0604")
            session.add(admin)

            # Init lifetime stats for admin
            stats = LifetimeStats(user_id=1)
            session.add(stats)

        # Seed guest/demo viewer
        guest = session.query(User).filter_by(email="guest").first()
        if not guest:
            guest = User(
                email="guest",
                name="Guest",
                role="viewer",
                timezone="America/New_York",
            )
            guest.set_password("guest")
            session.add(guest)

        session.commit()
        print("[db] Users ready (gavin.roy07@ignitethelabel.com + guest)", flush=True)
    except Exception as e:
        session.rollback()
        print(f"[db] Init error: {e}", flush=True)
    finally:
        Session.remove()
