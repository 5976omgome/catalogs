"""Runtime configuration loaded from environment / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root if present
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# API credentials
DISCOGS_TOKEN: str = os.getenv("DISCOGS_TOKEN", "").strip()
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

# Server
PORT: int = int(os.getenv("PORT", "5000"))

# Paths
UPLOAD_DIR: Path = ROOT_DIR / "uploads"
OUTPUT_DIR: Path = ROOT_DIR / "Outputs"
CACHE_DB: Path = ROOT_DIR / "cache.db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# HTTP defaults
USER_AGENT = "CatalogAudit/2.0 (+https://github.com/5976omgome/catalogs)"
DEFAULT_TIMEOUT = 12  # seconds

# Audit defaults
TOP_N_RELEASES = 3  # how many recent releases per artist to inspect
