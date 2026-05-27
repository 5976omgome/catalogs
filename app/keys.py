"""Runtime keys store. Keys live at ~/.catalog_audit/keys.json (mode 0600)
and are never committed to the repo. The web UI writes here through the
/api/settings endpoints; callers read through the get/get_all helpers.

Example:
    >>> set_key("discogs_token", "abcdefghijklmnopqrstuvwxyz")
    >>> get_key("discogs_token")
    'abcdefghijklmnopqrstuvwxyz'
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

_KEY_NAMES = ("discogs_token", "groq_api_key", "gemini_api_key")
_STORE_DIR = Path.home() / ".catalog_audit"
_STORE_PATH = _STORE_DIR / "keys.json"


def _read_disk() -> Dict[str, str]:
    if not _STORE_PATH.exists():
        return {}
    try:
        with _STORE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return {k: str(v) for k, v in data.items() if k in _KEY_NAMES}
    except Exception:
        return {}


def _write_disk(data: Dict[str, str]) -> None:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _STORE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f)
    tmp.replace(_STORE_PATH)
    try:
        os.chmod(_STORE_PATH, 0o600)
    except OSError:
        pass


def get_key(name: str) -> Optional[str]:
    """Returns the key from disk, falling back to env var. None if neither set."""
    if name not in _KEY_NAMES:
        return None
    disk = _read_disk().get(name, "").strip()
    if disk:
        return disk
    env_name = name.upper()
    env_val = os.environ.get(env_name, "").strip()
    return env_val or None


def set_key(name: str, value: str) -> None:
    """Saves the key to disk. Empty string clears it."""
    if name not in _KEY_NAMES:
        raise ValueError(f"unknown key: {name}")
    data = _read_disk()
    if value:
        data[name] = value
    else:
        data.pop(name, None)
    _write_disk(data)


def update_keys(updates: Dict[str, str]) -> None:
    """Bulk update. Only known key names are accepted."""
    if not isinstance(updates, dict):
        raise ValueError("updates must be a dict")
    data = _read_disk()
    for k, v in updates.items():
        if k not in _KEY_NAMES:
            continue
        v = (v or "").strip()
        if v:
            data[k] = v
        else:
            data.pop(k, None)
    _write_disk(data)


def clear_all() -> None:
    if _STORE_PATH.exists():
        _STORE_PATH.unlink()


def mask(value: Optional[str]) -> str:
    """Returns a short masked preview, e.g. abcd…wxyz, never the full secret."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}\u2026{value[-4:]}"


def status() -> Dict[str, Dict[str, object]]:
    """For the UI: which keys are set, where they came from, and a masked preview."""
    out: Dict[str, Dict[str, object]] = {}
    disk = _read_disk()
    for name in _KEY_NAMES:
        d = disk.get(name, "").strip()
        e = os.environ.get(name.upper(), "").strip()
        if d:
            out[name] = {"set": True, "source": "ui", "preview": mask(d)}
        elif e:
            out[name] = {"set": True, "source": "env", "preview": mask(e)}
        else:
            out[name] = {"set": False, "source": None, "preview": ""}
    return out
