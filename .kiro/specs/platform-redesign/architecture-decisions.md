# Platform Architecture Decisions
## IGNITE Virtual Scout — Full Platform Redesign

Synthesized from 40 answered questions. This is the authoritative spec.

---

## 1. IDENTITY & PURPOSE

**Platform Name**: IGNITE Virtual Scout  
**Tagline**: Catalog Scouting System  
**Owner**: IGNITE The Label (Mostafa Alsayed, Beirut/Global)  
**Purpose**: Find independent artists who own their catalogs, verify ownership, extract contacts, and qualify them for licensing/buyout/A&R outreach.

**Daily workflow**:
1. Import Chartmetric export (CSV of artists 250K–2M monthly streams)
2. Run Chartporter (audit ownership via iTunes/Deezer labels)
3. Run Genitractor (pull IG/FB from Genius)
4. Manually review → qualify → outreach

---

## 2. AUTHENTICATION

| Decision | Choice |
|----------|--------|
| Auth type | Real email/password (bcrypt hashed) |
| Multi-user | Yes (primary user + demo viewers) |
| Session | HTTP-only secure cookies (Flask-Login or JWT in cookie) |
| Password reset | Email-based token flow |
| Cloud sync | Future consideration (Google Drive for backups) |
| User fields | Email, password, name, role (admin/viewer) |

---

## 3. NAVIGATION & LAYOUT

### Sidebar (Left, Collapsible, Dark)

```
┌─────────────────────────┐
│ [IGNITE LOGO]           │  ← Icon only when collapsed
│ Virtual Scout           │  ← Text appears on expand
│ Contact Extraction      │
│              [00:00:00] │  ← Clock on right
├─────────────────────────┤
│ ◉ Dashboard             │  ← Logo icon when collapsed
│ ⚙ Settings              │  ← Gear icon when collapsed
├─────────────────────────┤
│ LIBRARY                 │  ← Section header (line when collapsed)
│   ▪ Artists             │
├─────────────────────────┤
│ TOOLS                   │  ← Section header (line when collapsed)
│   ▪ Chartporter         │
│   ▪ Genitractor         │
└─────────────────────────┘
```

**Behavior**:
- Collapsed: Icons only + line dividers for headers
- Expanded: Full text animates in (smooth slide)
- Dark theme matching tool pages
- Fixed position, content area scrolls independently

### Pages

| Route | Content |
|-------|---------|
| `/login` | Auth page (no sidebar) |
| `/dashboard` | Widgets + IGNITE mission info |
| `/settings` | API keys (4 Genius, 1 Groq, 1 Gemini, 1 Deezer, 1 iTunes) + timezone + export format |
| `/artists` | Master artist library table (imported CSVs) |
| `/tools/chartporter` | Existing Chartporter (wrapped in new shell) |
| `/tools/genitractor` | Existing Genitractor (wrapped in new shell) |

---

## 4. DASHBOARD

### Widgets (Cards/Tiles)

| Widget | Data Source | Description |
|--------|-------------|-------------|
| Total Processed | Lifetime sum from Chartporter + Genitractor runs | Cumulative artists processed across all time |
| Total % Yield | (clean% + found%) / total lifetime processed | Account-local cached metric |
| Emails Sent | Manual counter or integration | Tracks outreach from 2 scouting email accounts |
| API Usage | Per-key request counters | Shows remaining capacity / rate limit status |

### Content Below Widgets
- IGNITE mission statement (from website §01 Doctrine)
- Platform purpose summary (from the scouting outline)
- Quick-access shortcuts to Tools

### Color Palette: "Crimson Hues"
- Background: `#250902` (Rich Mahogany)
- Cards/surfaces: `#38040e` (Rich Mahogany lighter)
- Accent: `#640d14` (Black Cherry)
- Highlight: `#800e13` (Dark Wine)
- Active/CTA: `#ad2831` (Brown Red)
- Text: White / `#f0eff4` (Ghost White)

---

## 5. SETTINGS PAGE

### API Key Slots

| Service | Slots | Used By |
|---------|-------|---------|
| Genius | 4 | Genitractor (auto-rotate on rate limit) |
| Groq | 1 | Chartporter AI bridge |
| Gemini | 1 | Chartporter AI bridge |
| Deezer | 1 | Chartporter ownership check |
| iTunes | 1 | Chartporter ownership check |

**Behavior**:
- Auto-rotation: Genius keys cycle round-robin when one hits rate limit
- Validation: On save, test key against respective API → show ✓ (green) or ✗ (red)
- Masked display after save (show last 4 chars only)

### Other Settings
- Timezone selector
- Export format: Column picker (select which columns appear in CSV exports)
- "Insert" section: Paste area for any config the platform needs

### Color Palette: "Cozy Neutrals"
- Background: `#e9e3e6` (Alabaster Grey)
- Cards: `#ffffff` or `#f5f3f4`
- Borders: `#c3baba` (Silver)
- Text: `#736f72` (Dim Grey)
- Labels: `#9a8f97` (Rosy Granite)
- Inputs: White with `#b2b2b2` borders

---

## 6. ARTISTS PAGE (Library)

### Data Model — Core Columns

| Column | Source | Required |
|--------|--------|----------|
| Artist Name | CSV import | ✓ |
| Type | CSV (Solo/Group) | |
| Emails | Genitractor export or manual | |
| Instagram | Genitractor export | |
| Spotify | CSV (Spotify Links) | |
| Monthly (Listeners) | CSV | |
| Growth/Momentum | CSV (Recent Momentum) | |
| Status | User-assigned (Email Sent / Follow Up / Moving Forward / Not Sent / Wrong Email) | |
| Label Info | CSV (Associated Labels + Label Category) | |
| Region | CSV | |
| Genre/Scene | CSV (Genres) | |

### Extended Columns (from Chartmetric export, appended)
Chartmetric ID, Country, Continent, Pronouns, Solo/Group, Moods, Activities, Career Stage, Spotify Followers, Instagram Followers, Instagram Engagement Rate, First Release Date, Latest Release Date

### Extra Imported Columns
Any columns in the CSV that don't match known columns → appended at the end as-is.

### Table Features
- **Super customizable**: Show/hide any column via column picker
- **Sortable**: Click header to sort ASC/DESC
- **Filterable**: 
  - Momentum filter (Growth / Steady / Slowing / Explosive Growth / Cooling)
  - Monthly listener range slider
  - Release date range
  - Region/Genre multi-select
  - Status filter
  - Add/remove columns from view
- **Batch labels**: Tag artists with date-based batch labels ("week of 05/31")
- **Status tracking**: Per-artist status (Email Sent, Follow Up Sent, Moving Forward, Not Sent, Wrong Email)
- **Pagination**: Handle 20,000+ rows efficiently (virtualized or paginated)
- **Export**: Download visible/filtered rows as CSV with selected columns only

### Color Palette: "Gothic Glam"
- Background: `#000000` (Black)
- Cards/table: `#3d2645` (Midnight Violet) surface
- Row hover: `#832161` (Royal Plum)
- Active/selected: `#da4167` (Magenta Bloom)
- Text: `#f0eff4` (Ghost White)
- Headers: White on dark
- Empty state: Subtle plum gradients

---

## 7. TOOLS (Chartporter & Genitractor)

### Wrapper Approach
- Same existing functionality (upload CSV → process → export)
- Wrapped inside the new platform shell (sidebar visible)
- Keep existing queue bar, feed, system console, timer, stats
- Keep existing animations + fix reported bugs (system hides after run, feed has 0 animation)

### Tool History
- Log of past runs: date, filename, results count, duration
- Accessible from the tool page (collapsible history panel)
- Used by dashboard widgets for lifetime stats

### Integration with Library
- No auto-save (Library is manually curated)
- User can manually import Chartporter/Genitractor exports into Library

### API Key Rotation (Genitractor)
- When Genius key 1 hits rate limit → automatically switch to key 2 → 3 → 4 → back to 1
- Display which key is active in the tool status

---

## 8. REPORTS

### Format
- Professional, short summary report
- Presentable to boss (Mostafa)
- Content:
  - Date range
  - Artists processed (Chartporter + Genitractor)
  - Yield rates (% Clean, % Found)
  - Top qualified artists (KEEP with contacts)
  - Outreach pipeline status (how many in each status)
- Export as: PDF or formatted printable HTML

---

## 9. TECHNICAL STACK

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | **React** (Vite bundler) | Complex SPA with multiple routes, highly interactive tables, component reuse |
| Routing | React Router v6 | SPA client-side routing |
| State | React Context + useReducer (or Zustand) | Lightweight, no Redux overhead |
| Styling | CSS Modules or Tailwind + custom design tokens | Per-page color palettes |
| Tables | TanStack Table (React Table v8) | Virtualization, sorting, filtering, column visibility — handles 20k+ rows |
| Backend | **Flask** (existing, extended) | Keep all existing audit/genius/export logic |
| Database | **SQLite** (via SQLAlchemy) | Best free DB, single-file, zero config, good for single-user, encrypted at rest with sqlcipher if needed |
| Auth | Flask-Login + bcrypt + secure cookies | Simple, proven |
| Real-time | **WebSockets** (flask-socketio) | Upgrade from SSE for bidirectional, better reconnection |
| Deployment | **Electron** wrapper (or Docker for server) | Desktop-app feel ("like Steam"), instant updates, local-first |
| Build | Vite (frontend) + pip (backend) | Fast dev, HMR for React |

### Database Schema (SQLite)

```sql
-- Users
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    role TEXT DEFAULT 'viewer',  -- admin, viewer
    timezone TEXT DEFAULT 'America/New_York',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API Keys
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    service TEXT NOT NULL,  -- genius, groq, gemini, deezer, itunes
    slot INTEGER DEFAULT 1,  -- 1-4 for genius, 1 for others
    key_value TEXT NOT NULL,  -- encrypted
    is_valid BOOLEAN DEFAULT NULL,
    last_validated TIMESTAMP,
    requests_today INTEGER DEFAULT 0
);

-- Artists (Library)
CREATE TABLE artists (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    artist_name TEXT NOT NULL,
    type TEXT,  -- Solo/Group
    emails TEXT,
    instagram TEXT,
    spotify_link TEXT,
    monthly_listeners INTEGER,
    momentum TEXT,  -- Growth/Steady/Slowing/etc
    status TEXT DEFAULT 'Not Sent',  -- Email Sent/Follow Up/Moving Forward/Not Sent/Wrong Email
    label_info TEXT,
    region TEXT,
    genre TEXT,
    batch_label TEXT,  -- "week of 05/31"
    batch_date DATE,
    extra_data JSON,  -- All non-standard columns stored as JSON
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Tool Runs (History)
CREATE TABLE tool_runs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tool TEXT NOT NULL,  -- chartporter, genitractor
    filename TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    total_artists INTEGER DEFAULT 0,
    processed INTEGER DEFAULT 0,
    keep_count INTEGER DEFAULT 0,
    review_count INTEGER DEFAULT 0,
    drop_count INTEGER DEFAULT 0,
    found_count INTEGER DEFAULT 0,
    status TEXT  -- running, done, stopped, error
);

-- Lifetime Stats (for widgets)
CREATE TABLE lifetime_stats (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    total_processed INTEGER DEFAULT 0,
    total_keep INTEGER DEFAULT 0,
    total_found INTEGER DEFAULT 0,
    emails_sent INTEGER DEFAULT 0,
    updated_at TIMESTAMP
);
```

---

## 10. COLOR SYSTEM (Design Tokens)

```css
/* Dashboard — Crimson Hues */
--dash-bg: #250902;
--dash-surface: #38040e;
--dash-accent: #640d14;
--dash-highlight: #800e13;
--dash-cta: #ad2831;

/* Artists — Gothic Glam */
--artists-bg: #000000;
--artists-surface: #3d2645;
--artists-hover: #832161;
--artists-active: #da4167;
--artists-text: #f0eff4;

/* Settings — Cozy Neutrals */
--settings-bg: #e9e3e6;
--settings-surface: #ffffff;
--settings-border: #c3baba;
--settings-text: #736f72;
--settings-label: #9a8f97;

/* Sidebar — Muted Earthy Tones */
--sidebar-bg: #6d6875;
--sidebar-hover: #b5838d;
--sidebar-active: #e5989b;
--sidebar-text: #ffcdb2;
--sidebar-accent: #ffb4a2;

/* Shared */
--text-primary: #f0eff4;
--text-muted: #b2b2b2;
--success: #4ade80;
--warning: #fbbf24;
--error: #ef4444;
```

---

## 11. ANIMATIONS & UX

### New
- Sidebar collapse/expand: smooth width transition (200ms ease)
- Page transitions: fade + slight translateX between routes
- Table row hover: background color shift (100ms)
- Widget cards: subtle scale on hover (1.02)
- Modal open/close: scale from 0.95 + opacity
- Loading states: skeleton shimmer on tables/cards

### Fixed from Current
- System console: no longer hides after files run — stays visible with results
- Feed: proper enter animation for new blocks (slide in from left)
- Dropdown animations: CSS-only transitions (no JS setTimeout conflicts)

---

## 12. DEPLOYMENT STRATEGY

**Primary**: Electron desktop app (cross-platform, auto-update via electron-updater)
- Frontend: React (Vite build → static files)
- Backend: Flask server bundled inside Electron (runs on localhost)
- Database: SQLite file in user's app data directory
- Updates: GitHub Releases + electron-updater (like Steam auto-patching)

**Alternative** (if Electron is too heavy): Docker container with `docker-compose up`
- Same architecture, just containerized
- Access via `localhost:5000` in browser

**Decision**: Start with Docker (simpler to develop), convert to Electron later if desired.

---

## 13. MIGRATION PATH

Current state → New platform:

1. Keep ALL existing Flask routes (server.py, jobs.py, sources/*)
2. Add new routes: `/api/auth/*`, `/api/artists/*`, `/api/stats/*`, `/api/reports/*`
3. Add SQLite database layer (SQLAlchemy models)
4. Build React frontend that consumes the Flask API
5. Existing tool pages (Chartporter/Genitractor) become React components
6. Existing CSS is preserved inside tool components (scoped)
7. New pages (Dashboard, Settings, Artists) use new design tokens

No breaking changes to existing tool logic.
