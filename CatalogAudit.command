#!/usr/bin/env bash
# Catalog Audit launcher (macOS / Linux)
# Double-click this file to start the app. It will open in your default browser.

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Pick a Python: prefer python3, fall back to python.
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/"
  read -n 1 -s -r -p "Press any key to exit..."
  exit 1
fi

# Create a virtualenv on first run.
if [ ! -d ".venv" ]; then
  echo ">> Creating virtual environment (.venv)..."
  "$PY" -m venv .venv
fi

# Activate it.
# shellcheck disable=SC1091
source .venv/bin/activate

# Install dependencies if needed.
if [ ! -f ".venv/.installed" ] || [ "requirements.txt" -nt ".venv/.installed" ]; then
  echo ">> Installing dependencies..."
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
  touch ".venv/.installed"
fi

# Friendly notice if .env is missing.
if [ ! -f ".env" ]; then
  echo ">> No .env found. Copying .env.example -> .env (edit it to add your API keys)."
  cp .env.example .env
fi

echo ">> Starting Catalog Audit..."
echo ">> Browser will open at http://127.0.0.1:5000"
python run.py
