"""Entrypoint. Boots the Flask app under Waitress, opens the browser."""
from __future__ import annotations

import socket
import threading
import time
import webbrowser

from app.server import app


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _pick_port(start: int = 5000, tries: int = 10) -> int:
    for offset in range(tries):
        candidate = start + offset
        if _port_available(candidate):
            return candidate
    raise RuntimeError(f"No free port in range {start}-{start + tries - 1}")


def _open_browser_later(url: str, delay: float = 1.5) -> None:
    def _go() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_go, daemon=True).start()


def main() -> None:
    from waitress import serve

    port = _pick_port(5000)
    url = f"http://127.0.0.1:{port}"
    print(f"Catalog Audit running at {url}")
    print("Press Ctrl+C to stop.")
    _open_browser_later(url)
    try:
        serve(app, host="127.0.0.1", port=port, threads=8)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
