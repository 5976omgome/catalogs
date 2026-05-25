@echo off
REM Catalog Audit launcher (Windows)
REM Double-click this file to start the app. It will open in your default browser.

setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is not installed or not on PATH.
  echo Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo ^>^> Creating virtual environment (.venv)...
  python -m venv .venv
)

call .venv\Scripts\activate.bat

if not exist .venv\.installed (
  echo ^>^> Installing dependencies...
  python -m pip install --upgrade pip >nul
  pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
  )
  type nul > .venv\.installed
)

if not exist .env (
  echo ^>^> No .env found. Copying .env.example to .env (edit it to add your API keys).
  copy /Y .env.example .env >nul
)

echo ^>^> Starting Catalog Audit...
echo ^>^> Browser will open at http://127.0.0.1:5000
python run.py

endlocal
