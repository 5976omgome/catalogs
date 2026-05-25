# Catalog Audit

A local web app that scans a Chartmetric artist export and flags anyone
who is **not** fully self-released, so you only have to manually verify
the small handful that look clean.

It cross-checks three sources for every artist and asks an LLM for a
single-sentence verdict:

| Source | What it tells us |
| --- | --- |
| Chartmetric (the CSV you exported) | What the artist self-reports |
| **Deezer** (free, no auth) | Current streaming label on recent releases |
| **Discogs** (free token) | Historical catalog & physical-release labels |
| **Groq / Gemini** (free tier) | Plain-English `CLEAN` / `CAUTION` / `FLAGGED` verdict |

Output is an `.xlsx` next to the input file with these columns:

`Artist · Spotify Links · Genres · Region · Spotify Monthly Listeners ·
Associated Labels · Recent Momentum · Deezer Labels Found ·
Discogs Labels Found · Ever Signed · Flag · AI Verdict · AI Reason`

Rows colored green (clean), yellow (caution), red (flagged).

---

## Quick start

### 1. Install Python 3.10+

- **Windows:** <https://www.python.org/downloads/> — tick "Add Python to PATH" during install.
- **macOS:** already installed, or `brew install python`.

### 2. Get this folder on your computer

Either clone it with git, or download the repo as a zip from GitHub and
unzip it somewhere convenient (Desktop is fine).

### 3. Add your API keys

Open `.env.example`, save a copy as `.env`, and fill in:

```env
DISCOGS_TOKEN=your_discogs_personal_access_token
GROQ_API_KEY=your_groq_key
```

- **Discogs token** (free, no card): <https://www.discogs.com/settings/developers> → "Generate new token"
- **Groq key** (free tier, no card): <https://console.groq.com/keys>
- *(Optional)* **Gemini key** as a second AI fallback: <https://aistudio.google.com/app/apikey>

If you skip the Groq/Gemini keys, the app falls back to a deterministic
rule-based verdict — still useful, just less nuanced.

### 4. Launch

- **macOS:** double-click `CatalogAudit.command`
  - First time only, in Terminal: `chmod +x CatalogAudit.command`
- **Windows:** double-click `CatalogAudit.bat`

Either launcher will:

1. Create a `.venv/` virtual environment (first run only)
2. Install dependencies (first run only)
3. Start the local server
4. Open your browser at <http://127.0.0.1:5000>

### 5. Use it

1. Drop one or more Chartmetric CSV exports into the **QUEUE** card.
2. Click **RUN QUEUE**.
3. Watch the live log. Each artist gets `CLEAN`, `CAUTION`, or `FLAGGED`.
4. When a job finishes, click **download** in the queue, or **OPEN OUTPUTS FOLDER**.

---

## What the verdicts mean

- **CLEAN** — All three sources show self-released or distributor-only.
  These are your strongest candidates. **Still verify the P-line on Spotify** before reaching out.
- **CAUTION** — Mixed signals or a label name that diverges from the artist name without a clear self-release pattern. Worth a manual check.
- **FLAGGED** — A known major or established indie label was detected on at least one release. Probably not a fit for buyout / licensing deals.

The `Flag` column shows exactly which source and which release triggered the flag, so you can audit the AI's reasoning.

---

## Architecture

```
catalogs/
├── run.py                   # entrypoint: starts server, opens browser
├── requirements.txt
├── .env.example
├── CatalogAudit.command     # macOS / Linux launcher
├── CatalogAudit.bat         # Windows launcher
└── app/
    ├── server.py            # Flask + SSE
    ├── jobs.py              # background queue + event bus
    ├── audit.py             # per-artist pipeline
    ├── ai.py                # Groq -> Gemini -> rule-based fallback
    ├── labels.py            # majors / indies / distributors / self-release rules
    ├── cache.py             # SQLite cache for label lookups
    ├── http.py              # shared requests session w/ retries
    ├── excel.py             # .xlsx writer with row colors
    ├── config.py            # env vars + paths
    ├── sources/
    │   ├── deezer.py
    │   └── discogs.py
    ├── templates/index.html
    └── static/
        ├── app.js
        └── style.css
```

The audit pipeline is a pure function: `audit_artist(name, chartmetric_label) -> ArtistAudit`.
You can import it from a notebook or another script if you want to embed it elsewhere.

---

## Building a true .exe / .app (optional)

If you want a single double-clickable file with no Python prompt at all:

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --name CatalogAudit \
  --add-data "app/templates:app/templates" \
  --add-data "app/static:app/static" \
  run.py
```

(On Windows replace the `:` with `;` in `--add-data`.)

The result lands in `dist/CatalogAudit` (or `dist/CatalogAudit.exe`).
That binary still expects a `.env` file next to it.

---

## Tips

- **Clear cache** in the footer if you want to force fresh API calls.
  By default, lookups are cached for 30 days.
- **Re-runs are instant** for already-scanned artists thanks to the cache.
- The app caps the log at the last 2,000 lines so it never gets sluggish.
- Use **CLEAR FINISHED** to remove completed jobs from the queue display.
