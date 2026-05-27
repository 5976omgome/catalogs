# Catalog Audit

Local Flask web app that audits a Chartmetric CSV export and classifies each artist
as KEEP / REVIEW / DROP for catalogue acquisition outreach. Pulls label data from
Apple iTunes (P-line), Deezer, Discogs, plus the Chartmetric self-reported label.

## Setup (macOS)

```bash
cd ~/Desktop
git clone https://github.com/5976omgome/catalogs.git
cd catalogs
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

Browser opens to http://127.0.0.1:5000.

Paste your Discogs / Groq / Gemini keys into the **API KEYS** card at the top
of the page (keys are stored at `~/.catalog_audit/keys.json`, mode 0600, never
in the git repo).

## Run again later

```bash
cd ~/Desktop/catalogs && source .venv/bin/activate && python run.py
```

## What the verdicts mean

- **KEEP** — every label across iTunes / Deezer / Discogs is either the artist's
  own name, a name variant (Drake → Drake Productions), or a known DIY distributor
  (DistroKid / TuneCore / CD Baby / etc).
- **REVIEW** — mixed signals (one platform shows a name variant, another shows
  unrelated third-party text). Worth a manual eyeball.
- **DROP_MAJOR** — major-family token detected (Universal / Sony / Warner /
  BMG / Disney / Hasbro family).
- **DROP_LICENSED** — exclusive-licensing language detected
  ("under exclusive license to X", "bajo Licencia Exclusiva...", etc).
- **DROP_THIRDPARTY** — releases on a third-party indie label that isn't a
  variant of the artist name.

## Buttons

- **RUN QUEUE** — start processing queued CSVs.
- **STOP** — finish the current artist, write a partial output, pause.
- **export keep / review / drops / all** — filtered xlsx download per finished
  job. Each export is a fresh slice of the original output sheet.
