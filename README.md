# Catalog Audit

A local web app that scans a Chartmetric artist export and flags anyone
who is **not** fully self-released, so you only have to manually verify
the small handful that look clean.

It cross-checks four sources for every artist and lets a small AI bridge
resolve trivial label-string differences when the rule engine is
otherwise being too literal.

| Source | Role |
| --- | --- |
| Chartmetric CSV (your input) | What the artist self-reports + `First Release Date` (used for the 2005 catalog-age cutoff) |
| **Apple iTunes** P-line | Ground truth. The legal phonographic copyright owner string. No auth required. |
| **Deezer** | Current streaming-label cross-check. No auth. |
| **Discogs** | Historical catalog cross-check. Free token. |
| **Groq / Gemini** *(optional)* | Bridges trivial string differences (e.g. "X Records" vs "X Recordings"). Cannot override hard flags. |

Output is an `.xlsx` with these columns:

`<all your input columns> · Apple P-Line · Apple Owners · Apple Licensed-To ·
Deezer Labels Found · Discogs Labels Found · First Release Year ·
Ever Signed · Has Licensing · Likely Self-Imprint · Flag · AI Verdict · AI Reason`

Plus a parallel `<filename>OutputCleanOnly.xlsx` containing only the rows
that came back CLEAN, for fast handoff.

Rows colored green (clean) or red (flagged). No rows are ever dropped.

---

## Verdict rules

A row is **CLEAN** only when ALL of these are true:

- iTunes P-line names only the artist (or a known DIY distributor)
- No "licensed to" / "exclusive licence to" clause anywhere
- No major or established indie label hit on any source
- No self-imprint pattern (e.g. "Artist Music", "Artist Records")
- Earliest release year is 2005 or later (from Chartmetric `First
  Release Date` if present, otherwise from the strict-name-matched
  iTunes / Deezer / Discogs lookup)

Anything else is **FLAGGED** with a specific reason in the `Flag` column.

The optional AI bridge is invoked only when the *only* reason for
flagging is a `DIVERGES` label-string mismatch. The bridge can upgrade
FLAGGED → CLEAN when it confirms the divergent strings are the same
entity (e.g. "Lyniel Records" vs "Lyniel Recordings"). The bridge can
**never** override a major-label hit, an indie-label hit, a licensing
clause, a self-imprint, or an old-catalog flag.

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
3. Watch the live log. Each artist gets `CLEAN` or `FLAGGED`.
4. Watch the two stat rows under the progress bar — the top one is run
   progress (`50 of 120 processed · 41%`), the bottom one is the live
   clean rate (`12 of 50 clean · 24%`).
5. When a job finishes, click **full** or **clean-only** in the queue,
   or **OPEN OUTPUTS FOLDER**.

---

## What the verdicts mean

- **CLEAN** — Every source agrees the artist is fully self-released, no
  label deals, post-2005 catalog. Strong candidates for buyout /
  licensing outreach. The Apple P-line column shows the literal legal
  string Apple has on file; you can still spot-check it visually.
- **FLAGGED** — Anything not clean. Read the `Flag` column for the
  specific reason: `MAJOR`, `INDIE`, `LICENSED-TO`, `DIVERGES`,
  `SELF_IMPRINT`, `OLD_CATALOG`. Self-imprints (artist-name + suffix
  patterns) are flagged on purpose — even though they're often
  self-released in practice, you said you want to manually review them
  rather than auto-clear.

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
