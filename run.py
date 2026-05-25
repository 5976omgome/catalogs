"""Catalog Audit launcher.

Starts the local Flask server and opens the browser at the right URL.
Works on macOS, Windows, and Linux without modification.
"""
from __future__ import annotations

import threading
import time
import webbrowser

from app.config import PORT
from app.server import run_server


def _open_browser_when_ready(url: str) -> None:
    # give the server a moment to bind
    time.sleep(1.2)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    url = f"http://127.0.0.1:{PORT}"
    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
    run_server()


if __name__ == "__main__":
    main()
