"""Configuration loaded from .env."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

_out = os.environ.get("OUTPUT_DIR", "").strip()
OUTPUT_DIR = Path(_out) if _out else (BASE_DIR / "Outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OLD_CATALOG_CUTOFF_YEAR = 2005

USER_AGENT = "CatalogAudit/1.0"
