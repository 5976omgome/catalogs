"""Central configuration — paths and live key accessors."""
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "Outputs"
UPLOAD_DIR = BASE_DIR / ".uploads"
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# Keys are read lazily so UI saves take effect without restart.
from app.keys import KeyStore  # noqa: E402

_store = KeyStore()


def groq_api_key() -> str:
    return _store.get("groq_api_key") or os.getenv("GROQ_API_KEY", "")


def gemini_api_key() -> str:
    return _store.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")


def keys_store() -> "KeyStore":
    return _store
