"""Configuration. Secrets live in app.keys (runtime); paths/constants here."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from . import keys

BASE_DIR = Path(__file__).resolve().parent.parent

_out = os.environ.get("OUTPUT_DIR", "").strip()
OUTPUT_DIR = Path(_out) if _out else (BASE_DIR / "Outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OLD_CATALOG_CUTOFF_YEAR = 2005

USER_AGENT = "CatalogAudit/1.0"


# --- Live secret accessors ---
# These return the current value at call time, so a UI save takes effect
# immediately without a restart. File (~/.catalog_audit/keys.json) wins;
# environment variables are an honored fallback.

def discogs_token() -> str:
    return keys.get("discogs_token")


def groq_api_key() -> str:
    return keys.get("groq_api_key")


def gemini_api_key() -> str:
    return keys.get("gemini_api_key")
