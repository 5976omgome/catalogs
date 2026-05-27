"""Live config readers. These functions are called per-request, never cached
at import time, so a UI key save takes effect on the very next call."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from . import keys

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "Outputs"
UPLOAD_DIR = BASE_DIR / ".uploads"
CACHE_DIR = BASE_DIR / ".cache"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def discogs_token() -> Optional[str]:
    return keys.get_key("discogs_token")


def groq_api_key() -> Optional[str]:
    return keys.get_key("groq_api_key")


def gemini_api_key() -> Optional[str]:
    return keys.get_key("gemini_api_key")


# Old-catalog cutoff. Per current spec this is INFORMATIONAL only,
# never gates the verdict — but the year is still surfaced on the row.
EARLIEST_YEAR_CUTOFF = 2005

DISCOGS_USER_AGENT = "CatalogAuditApp/1.0"

# Network timeouts in seconds. (connect, read).
HTTP_TIMEOUT = (5, 15)
