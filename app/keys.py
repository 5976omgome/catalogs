"""
Runtime API-key store.

Keys live in ~/.catalog_audit/keys.json (outside the repo).
File is created with 0600 perms on POSIX. Values are read on every
get_*() call so a Save in the UI takes effect without restart.

The repo never contains real keys. Environment variables (DISCOGS_TOKEN,
GROQ_API_KEY, GEMINI_API_KEY) are still honored as a fallback for users
who prefer env-based config.
"""
import json
import os
import threading
from pathlib import Path
from typing import Dict, Optional

_DIR = Path.home() / ".catalog_audit"
_FILE = _DIR / "keys.json"
_LOCK = threading.Lock()

_SUPPORTED = ("discogs_token", "groq_api_key", "gemini_api_key", "genius_token")


def _load() -> Dict[str, str]:
    if not _FILE.exists():
        return {}
    try:
        with _FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return {k: str(v) for k, v in data.items() if k in _SUPPORTED and v}
    except Exception:
        return {}


def _save(data: Dict[str, str]) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    # Tighten permissions on POSIX before atomic rename.
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(_FILE)
    try:
        os.chmod(_FILE, 0o600)
    except OSError:
        pass


def _env_fallback(name: str) -> str:
    env_name = name.upper()
    return (os.environ.get(env_name) or "").strip()


def get(name: str) -> str:
    """Return the live value for a key. File wins; env is fallback."""
    if name not in _SUPPORTED:
        return ""
    with _LOCK:
        data = _load()
    val = (data.get(name) or "").strip()
    if val:
        return val
    return _env_fallback(name)


def set_many(updates: Dict[str, Optional[str]]) -> None:
    """
    Update multiple keys at once.
    - Empty string means "clear this key".
    - None means "leave this key unchanged".
    Unknown names are ignored.
    """
    with _LOCK:
        data = _load()
        for k, v in updates.items():
            if k not in _SUPPORTED:
                continue
            if v is None:
                continue
            v = str(v).strip()
            if v == "":
                data.pop(k, None)
            else:
                data[k] = v
        _save(data)


def status() -> Dict[str, dict]:
    """
    Returns per-key status with a masked preview. Never returns full secrets.
    Source is one of: 'file', 'env', or 'unset'.
    """
    out: Dict[str, dict] = {}
    with _LOCK:
        file_data = _load()
    for name in _SUPPORTED:
        file_val = (file_data.get(name) or "").strip()
        env_val = _env_fallback(name)
        if file_val:
            out[name] = {
                "set": True,
                "source": "file",
                "preview": _mask(file_val),
            }
        elif env_val:
            out[name] = {
                "set": True,
                "source": "env",
                "preview": _mask(env_val),
            }
        else:
            out[name] = {"set": False, "source": "unset", "preview": ""}
    return out


def _mask(value: str) -> str:
    """Return a short masked preview like 'abcd…wxyz' (4 visible at each end)."""
    v = value.strip()
    if len(v) <= 10:
        return "*" * len(v)
    return f"{v[:4]}…{v[-4:]}"


def storage_path() -> str:
    return str(_FILE)
