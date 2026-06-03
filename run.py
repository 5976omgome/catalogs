"""Catalog Audit — entry point.
Run: python run.py
"""
import socket
import webbrowser
import threading

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
    port = find_open_port()
    url = f"http://127.0.0.1:{port}"
    print(f"Catalog Audit running at {url}")
    print("Press Ctrl+C to stop.")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=port, threads=4)
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
