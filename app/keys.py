"""Secure local key storage at ~/.catalog_audit/keys.json.
Owner-only permissions (0600). Never committed to git.
"""
import json
import os
from pathlib import Path
from typing import Optional

_DIR = Path.home() / ".catalog_audit"
_FILE = _DIR / "keys.json"

VALID_KEYS = ("discogs_token", "groq_api_key", "gemini_api_key")


def _mask(value: str) -> str:
    if not value or len(value) < 8:
        return "****" if value else ""
    return value[:4] + "\u2026" + value[-4:]


class KeyStore:
    def __init__(self):
        self._data: dict = {}
        self._load()

    def _load(self):
        if _FILE.exists():
            try:
                self._data = json.loads(_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self):
        _DIR.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps(self._data, indent=2))
        try:
            os.chmod(str(_FILE), 0o600)
        except OSError:
            pass

    def get(self, key: str) -> str:
        return self._data.get(key, "")

    def set(self, key: str, value: str):
        if key in VALID_KEYS:
            self._data[key] = value
            self._save()

    def clear(self, key: Optional[str] = None):
        if key:
            self._data.pop(key, None)
        else:
            self._data.clear()
        self._save()

    def status(self) -> dict:
        """Return masked status for each key (safe for HTTP responses)."""
        result = {}
        for k in VALID_KEYS:
            v = self._data.get(k, "")
            result[k] = {
                "set": bool(v),
                "preview": _mask(v),
                "source": "ui" if v else "env" if os.getenv(k.upper(), "") else "none",
            }
        return result
