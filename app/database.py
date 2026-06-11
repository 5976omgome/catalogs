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
    """Create all tables and seed the admin account if not present."""
    Base.metadata.create_all(engine)
    session = Session()
    try:
        # Seed admin user
        admin = session.query(User).filter_by(email="gavin@ignitethelabel.com").first()
        if not admin:
            admin = User(
                email="gavin@ignitethelabel.com",
                name="Gavin Roy",
                role="admin",
                timezone="America/New_York",
            )
            admin.set_password("0604")
            session.add(admin)

            # Init lifetime stats
            stats = LifetimeStats(user_id=1)
            session.add(stats)

            session.commit()
            print("[db] Admin account seeded: gavin@ignitethelabel.com", flush=True)
        else:
            print("[db] Database ready.", flush=True)
    except Exception as e:
        session.rollback()
        print(f"[db] Init error: {e}", flush=True)
    finally:
        Session.remove()
