"""Entry point: starts the Flask server via Waitress on http://127.0.0.1:5000

If port 5000 is already in use we try 5001, 5002, ... up to 5010 and
print a clear message. This avoids a confusing "Address already in use"
stack trace if the user has another dev server on 5000.
"""
import socket
import webbrowser
from threading import Timer

from waitress import serve

from app.server import create_app


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def main():
    host = "127.0.0.1"
    port = None
    for candidate in range(5000, 5011):
        if _port_is_free(host, candidate):
            port = candidate
            break
    if port is None:
        print("Could not find a free port between 5000 and 5010.")
        print("Close whatever is using those ports and try again.")
        return 1

    url = f"http://{host}:{port}"
    print(f"Catalog Audit running at {url}")
    print("Press Ctrl+C to stop.")

    try:
        Timer(1.5, lambda: webbrowser.open(url)).start()
    except Exception:
        # Browser launch is best-effort; the URL is in the terminal.
        pass

    app = create_app()
    serve(app, host=host, port=port, threads=8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
