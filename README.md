# Catalog Audit

A local web app that screens Chartmetric CSV exports for clean,
self-released artists worth approaching for licensing or buyout deals.

For every artist on a CSV it reads:

- Apple iTunes (free, no auth) - the legal P-line is the authoritative
  signal for who owns a master recording
- Deezer (free, no auth) - cross-reference for streaming-era catalog
- Discogs (free token, optional) - historical / physical-release labels
- Chartmetric self-reported `Associated Labels` and `First Release Date`

A strict rule engine then decides **CLEAN** or **FLAGGED** for each row.
A small AI tiebreaker (Groq -> Gemini -> deterministic) is used only to
bridge trivial label-string differences (e.g. "X Records" vs "X
Recordings"). The AI cannot override any major / indie / licensed-to /
old-catalog / self-imprint signal.

Output is an `.xlsx` with green CLEAN rows and red FLAGGED rows, plus
columns for the iTunes P-line, the licensee (if any), every Deezer and
Discogs label found, the earliest release year, and the precise reasons
for each flag.

## Run it on macOS

```bash
cd ~/Desktop
git clone -b feat/catalog-audit-rebuild-v2 https://github.com/5976omgome/catalogs.git
cd catalogs
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

The terminal will print `Catalog Audit running at http://127.0.0.1:5000`
and your browser opens automatically. To stop, press `Ctrl+C`.

## Run it on Windows

In PowerShell or Command Prompt:

```bat
cd %USERPROFILE%\Desktop
git clone -b feat/catalog-audit-rebuild-v2 https://github.com/5976omgome/catalogs.git
cd catalogs
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python run.py
```

## Setting your API keys

**There is no `.env` file to edit. You set your keys in the web UI.**

The page opens to an "API KEYS" card at the top:

- **Discogs token** - free, no card. Get one at
  https://www.discogs.com/settings/developers
- **Groq API key** - free, no card. Get one at
  https://console.groq.com/keys
- **Gemini API key** - free. Get one at
  https://aistudio.google.com/apikey

Paste a key into a field and click **SAVE KEYS**. The key is written to
`~/.catalog_audit/keys.json` with permissions `0600` and only the
masked preview (`abcd…wxyz`) is ever shown back in the page or returned
by the API. Saved keys take effect immediately, no restart needed.

Click **CLEAR ALL** to wipe every saved key on this machine.

If you prefer environment variables (CI runners, shared dev boxes),
copy `.env.example` to `.env` and set values there. UI-saved keys win
over env values for the same field.

### Which keys are required

- **None.** The audit runs with iTunes + Deezer alone. Verdicts will be
  somewhat stricter (no Discogs cross-check, AI bridge falls back to a
  deterministic loose-string compare) but nothing breaks.
- **Discogs** adds historical / physical-release label coverage.
- **Groq** (or **Gemini**) lets the AI bridge handle trivial
  label-string differences and reduces false-FLAGGED rates.

## How a row is judged

A row is **CLEAN** only when:

1. The iTunes P-line names only the artist or a known DIY distributor
   (DistroKid, CD Baby, TuneCore, etc.), with no licensing-to clause
2. Deezer / Discogs / Chartmetric labels also match (or come back
   empty), or the AI bridge confirms cross-source differences are just
   formatting variants
3. Earliest known release year is 2005 or later

Anything else is **FLAGGED**, with the precise reason written into the
output sheet (`MAJOR (Deezer): Atlantic`, `LICENSED-TO (iTunes):
Republic Records`, `OLD_CATALOG: earliest release 1990`,
`SELF_IMPRINT (Chartmetric): Krisu Music`, etc.).

Self-imprints (label name overlaps the artist name with extra words,
like "Krisu Music" or "Drake Music Group") are always flagged for
manual review and never auto-cleared by the AI - that's by design.

## Files in the repo

```
app/
  audit.py          strict rule engine (CLEAN/FLAGGED)
  ai_bridge.py      narrow AI tiebreaker for label-string differences
  excel.py          xlsx writer with green/red row coloring
  jobs.py           background queue + SSE event broadcast
  keys.py           runtime keys store (~/.catalog_audit/keys.json)
  labels.py         label classification + self-release detection
  server.py         Flask app, SSE streaming, /api/settings endpoints
  config.py         paths and live secret accessors
  cache.py          SQLite cache for API lookups (30-day TTL)
  sources/
    itunes.py       Apple iTunes Search (P-line)
    deezer.py       Deezer API
    discogs.py      Discogs API
static/
  index.html        UI shell (API KEYS card, queue, progress, log)
  app.js            wires the UI, talks to /api/* and SSE
  style.css         dark / hacker-green styling
run.py              entry point: serves on http://127.0.0.1:5000
requirements.txt
.env.example        optional env-var overrides (the UI is the primary path)
```

## Output

For every CSV you queue, the app writes
`Outputs/<csv-stem>Output.xlsx` next to the source. Each row contains
the original Chartmetric columns plus:

- **Verdict** - `CLEAN` or `FLAGGED`
- **Earliest Year** - the smallest year across Chartmetric / iTunes /
  Deezer / Discogs strict-name-matched releases
- **iTunes P-Line** - the literal copyright string from Apple
- **iTunes Licensee** - extracted licensee if a "under exclusive
  licence to ..." clause is present
- **Deezer Labels** / **Discogs Labels** - pipe-separated
- **Likely Self-Imprint** - `yes` if the label looks like the artist's
  own imprint
- **Flag Reasons** - every reason that contributed to the verdict

CLEAN rows are colored green, FLAGGED rows red.
