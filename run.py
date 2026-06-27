"""Virtual Scout — entry point.
Run: python run.py

Data persistence:
- On startup, if this install has no database yet (a fresh clone) but a
  ~/Downloads/ignite_backup.db safety copy exists, we RESTORE from it first —
  so your artists and saved API keys come back automatically.
- We then keep a fresh backup in ~/Downloads on every launch, but never
  overwrite a good backup with an empty database.
The database lives in ./data/ (git-ignored), so `git pull` never touches it.
"""
import socket
import shutil
import webbrowser
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Restore BEFORE importing the app (importing app.server initializes the DB).
# ---------------------------------------------------------------------------
_DB = Path(__file__).resolve().parent / "data" / "ignite.db"
_BACKUP = Path.home() / "Downloads" / "ignite_backup.db"


def _restore_db_if_needed():
    """Seed a fresh/empty install from the ~/Downloads backup, if present."""
    try:
        missing_or_empty = (not _DB.exists()) or _DB.stat().st_size == 0
        if missing_or_empty and _BACKUP.exists() and _BACKUP.stat().st_size > 0:
            _DB.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(_BACKUP), str(_DB))
            print(f"[restore] Loaded your data from {_BACKUP}")
    except Exception as e:
        print(f"[restore] skipped ({e})")


_restore_db_if_needed()

from app.server import app  # noqa: E402  (after restore, so init_db sees your data)


def find_open_port(start: int = 5000, tries: int = 10) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _artist_count() -> int:
    """How many artists are in the DB (used to avoid backing up an empty DB)."""
    try:
        from app.database import Session, Artist
        s = Session()
        try:
            return s.query(Artist).count()
        finally:
            Session.remove()
    except Exception:
        return 0


def _backup_db():
    """Safety copy to ~/Downloads — but NEVER clobber a good backup with an
    empty database (protects your data if the app ever starts blank)."""
    try:
        downloads = Path.home() / "Downloads"
        if _DB.exists() and downloads.exists() and _artist_count() > 0:
            shutil.copy2(str(_DB), str(downloads / "ignite_backup.db"))
            print("[backup] DB saved to ~/Downloads/ignite_backup.db")
        else:
            print("[backup] skipped (no artists yet — keeping existing backup safe)")
    except Exception:
        pass


def main():
    _backup_db()

    port = find_open_port()
    url = f"http://127.0.0.1:{port}"
    print(f"Virtual Scout running at {url}")
    print("Press Ctrl+C to stop.")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=port, threads=16)
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
