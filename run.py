"""Entry point: starts the Flask server via Waitress on http://127.0.0.1:5000"""
import sys
import webbrowser
from threading import Timer

from waitress import serve

from app.server import create_app


def main():
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"
    print(f"Catalog Audit running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        Timer(1.5, lambda: webbrowser.open(url)).start()
    except Exception:
        pass
    app = create_app()
    serve(app, host=host, port=port, threads=8)


if __name__ == "__main__":
    main()
