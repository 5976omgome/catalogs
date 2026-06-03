# Catalog Audit

Automated label-ownership verification for catalog acquisition scouting.

Pulls P-line / label data from **iTunes**, **Deezer**, **Discogs**, and compares
against **Chartmetric** exports. Classifies each artist as:

- **KEEP** — self-released, owns masters, no label encumbrances
- **DROP_MAJOR** — major label detected
- **DROP_LICENSED** — exclusive licensing clause detected
- **DROP_THIRDPARTY** — third-party indie label (not a name variant)
- **REVIEW** — mixed signals, needs manual check

## Quick Start

```bash
cd ~/Desktop
git clone -b feat/catalog-audit-v4 https://github.com/5976omgome/catalogs.git
cd catalogs
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

Browser opens to `http://127.0.0.1:5000`.
Paste API keys in the UI, drop a Chartmetric CSV, hit RUN.

## Run again later

```bash
cd ~/Desktop/catalogs && source .venv/bin/activate && python run.py
```
