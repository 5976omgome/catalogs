"""Virtual Scout — entry point.
Run: python run.py
"""
import socket
import shutil
import webbrowser
import threading
from pathlib import Path

from app.server import app


def find_open_port(start: int = 5000, tries: int = 10) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def main():
    # Auto-backup DB to Downloads on every startup (safety copy)
    db_file = Path(__file__).parent / "data" / "ignite.db"
    downloads = Path.home() / "Downloads"
    if db_file.exists() and downloads.exists():
        backup = downloads / "ignite_backup.db"
        try:
            shutil.copy2(str(db_file), str(backup))
            print(f"[backup] DB saved to ~/Downloads/ignite_backup.db")
        except Exception:
            pass

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
