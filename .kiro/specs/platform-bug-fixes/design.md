# Platform Bug Fixes — Bugfix Design

## Overview

This design formalizes the fixes for the 20 confirmed defects in the **catalogs** platform (clauses
1.1–1.20 / expected 2.1–2.20 / preserved 3.1–3.9 in `bugfix.md`). The platform is a single Flask
process (`run.py` → `app/server.py`) hosting two tools that share one SSE/job backbone:

- **Chartporter** — `app/static/index.html` + `app/static/app.js`, backed by `app/jobs.py` (`JobManager`/`JobItem`).
- **Genitractor** — `app/static/genitractor.html` + `app/static/genitractor.js`, backed by the
  `_geni_*` globals and `/api/genitractor/*` routes in `app/server.py`.

The bugs cluster into ten concern-areas. The unifying root cause behind most of them is that
**client-side state is treated as the source of truth** (timers, counters, totals) and is therefore
lost on the SSE reconnect that happens on every page-switch/refresh, while **server-side state is
mutated without consistent locking** and **exports read styled `.xlsx` and in-progress files**. The
fix strategy is:

1. Make the **server** the source of truth for run start-time and progress counts, and ship those
   through the SSE `snapshot` and `/api/cross-status` so the client restores rather than re-derives.
2. Add the missing **Clear** controls and the missing Genitractor clear endpoint.
3. Replace styled `.xlsx` exports with **plain CSV** (Python `csv`, `text/csv`) across every variant,
   keeping the same columns and filters; surface export failures as **persistent in-UI messages**.
4. Harden the **Genius** request path (reconciled interval, escalating backoff, periodic pause,
   cross-pass mutual exclusion).
5. Make the front-end **init resilient** (per-init `try/catch`), fix the **collapsible** mechanism,
   guard **divide-by-zero**, **cap the feed DOM**, and route all shared Genitractor field access
   through `_geni_lock` with export reading only completed outputs.

The audit/classification logic, the unaffected modals, the SSE event semantics, and the Chartporter
concurrency model are explicitly out of scope and must remain unchanged (see *Preservation
Requirements* and clauses 3.x).

This work targets the running app under `app/` on branch **`feat/catalog-audit-v5`**.

## Glossary

- **Bug_Condition (C)**: The set of inputs/states that trigger a given defect (e.g. "a run is active
  and the page is refreshed"). Each concern-area below defines its own `isBugCondition`.
- **Property (P)**: The desired observable behavior for inputs where `C` holds (e.g. "the timer
  resumes from the server start time").
- **Preservation (¬C)**: Inputs where the bug condition does NOT hold; the fixed code must behave
  identically to the original for these (e.g. a single uninterrupted session, a normal-sized run).
- **`JobManager` / `JobItem`**: The Chartporter job model in `app/jobs.py`. `JobItem.to_dict()` is the
  payload shipped in SSE events and the `snapshot`.
- **`_geni_items`**: The Genitractor item list (list of dicts) in `app/server.py`, guarded by
  **`_geni_lock`**; `_geni_item_dict()` builds the SSE payload.
- **SSE snapshot**: The `{"type":"snapshot","items":[...]}` event sent to every new subscriber
  (`JobManager.subscribe()` / `geni_stream`). This is the only state a freshly-loaded page receives,
  so anything the client must restore on refresh has to live here.
- **Server-truth counts**: `processed/total/keep/review/drop` (Chartporter) and
  `processed/total/found` (Genitractor) computed and held server-side.
- **Genius-consuming passes**: `_genius_worker` (the post-audit social pass in `server.py`) and
  `_geni_worker` (the Genitractor extraction worker), both of which call `genius.get_socials()`.

## Bug Details

This section defines the bug condition for each of the ten concern-areas. Concrete file/function
references are in *Hypothesized Root Cause*; the fixes are in *Fix Implementation*.

### Bug Condition A — Elapsed timer freezes on navigation/refresh (1.1, 1.2)

The timer is driven only by `_timerStart=Date.now()`, set inside `startTimer()` which is only called
from the RUN click handler. A page-switch/refresh reloads the JS, resets `_timerStart=null`, and the
SSE `snapshot` carries no start time to restore from. The cross-tool timer element `#ctb-timer` exists
in markup but is never written by any code path.

```
FUNCTION isBugCondition_timer(input)
  INPUT: input = {run_active: bool, navigated_or_refreshed: bool, element: "#timer"|"#ctb-timer"}
  OUTPUT: boolean
  RETURN input.run_active
         AND ( (input.element == "#timer"     AND input.navigated_or_refreshed)
            OR (input.element == "#ctb-timer") )   // ctb-timer is never updated at all
END FUNCTION
```

**Examples**
- Start a Chartporter run, switch to Genitractor and back → `#timer` shows `00:00` (expected: resumes
  from real elapsed).
- Run on one tool, view the other → `#ctb-timer` stays `00:00` for the whole run (expected: ticks).
- Refresh mid-run → `#timer` dead (expected: resumes).
- Edge: a job that started 8 minutes ago, viewed in a freshly-opened tab → expected `08:xx`.

### Bug Condition B — No Clear control on either queue (1.3, 1.4)

Chartporter has a working backend (`/api/queue/clear` → `mgr.clear_done()`) but no UI button.
Genitractor has neither a button nor an endpoint, so `_geni_items` and per-item `_contacts` accumulate
for the server's lifetime.

```
FUNCTION isBugCondition_clear(input)
  INPUT: input = {tool: "chartporter"|"genitractor", wants_clear: bool}
  OUTPUT: boolean
  RETURN input.wants_clear
         AND ( clear_button_absent(input.tool)
            OR (input.tool == "genitractor" AND clear_endpoint_absent()) )
END FUNCTION
```

**Examples**
- Chartporter queue full of `done`/`error` items → no control to reset queue/feed/stats.
- Genitractor finished a run → contacts persist; no way to clear; a second run stacks on top.

### Bug Condition C — Export produces styled `.xlsx`, and "no output" UX is broken (1.5, 1.6, 1.20)

All exports go through `excel.py` (openpyxl: fonts, fills, widths, frozen panes) and are served as
`.xlsx`. When no completed output exists, Chartporter surfaces the failure only as a transient
`sys()` console line, and Genitractor navigates the browser to a raw JSON error page.

```
FUNCTION isBugCondition_export(input)
  INPUT: input = {tool, variant in {keep,review,drops,all,merge_all,contacts}, has_completed_output: bool}
  OUTPUT: boolean
  RETURN output_format(input) == "xlsx_styled"        // wrong format (1.20)
      OR (NOT input.has_completed_output               // broken empty-state UX (1.5/1.6)
          AND failure_surface(input.tool) IN {"transient_console","raw_json_page"})
END FUNCTION
```

**Examples**
- Export KEEP with completed output → today: styled `Foo-keep.xlsx`; expected: plain `Foo-keep.csv`.
- Chartporter EXPORT with zero completed items → today: a console line that scrolls away; expected: a
  persistent in-UI message.
- Genitractor EXPORT with no contacts → today: browser shows `{"error":"no contacts found yet"}`;
  expected: in-UI message, page unchanged.

### Bug Condition D — Genius runs too fast / no backoff / no cross-pass exclusion (1.7, 1.16)

`genius.py` sets `_MIN_INTERVAL = 0.5` while `_geni_worker`'s comment claims "0.25s"; on `429` it
retries once after a fixed 2s then gives up; Cloudflare `1015` and `403`-HTML bodies are not detected;
there is no periodic pause; and the two Genius-consuming passes can run simultaneously.

```
FUNCTION isBugCondition_genius(input)
  INPUT: input = {n_artists: int, response in {200,429,1015,403_html}, other_pass_active: bool}
  OUTPUT: boolean
  RETURN (input.response IN {429,1015,403_html} AND NOT escalating_backoff_applied())
      OR (input.n_artists is large AND NOT periodic_pause_applied())
      OR (input.other_pass_active AND NOT passes_mutually_excluded())
      OR interval_inconsistent_with_documented_value()
END FUNCTION
```

**Examples**
- 4000-artist run hits repeated `429`/`1015` → today: keeps hammering, swallows errors, stalls;
  expected: exponential backoff + pause-every-N, run completes.
- Genitractor run + Genius social pass started together → today: concurrent calls; expected:
  serialized.

### Bug Condition E — Inaccurate progress / found percentages after reconnect (1.8, 1.9, 1.10, 1.18)

Counters are accumulated purely from client SSE deltas (`_totalArtists`, per-feed `counts`,
`totalProcessed/totalArtists/totalFound`). The `snapshot` rebuilds feeds empty and does not restore
counts, so `% CLEAN` / `% FOUND` / `% TOTAL` desync after any reconnect. Separately, `/api/cross-status`
inflates Genitractor live totals by summing `done` items.

```
FUNCTION isBugCondition_stats(input)
  INPUT: input = {reconnected_midrun: bool, surface in {"%CLEAN","%FOUND","%TOTAL","cross"}}
  OUTPUT: boolean
  RETURN (input.reconnected_midrun AND input.surface IN {"%CLEAN","%FOUND","%TOTAL"}
          AND counts_not_restored_from_snapshot())
      OR (input.surface == "cross" AND cross_status_includes_done_items())
END FUNCTION
```

**Examples**
- 1000-artist run 60% done, refresh → `% TOTAL` shows `0%/…` then drifts; expected: ~60%.
- Cross bar after one tool finished and another starts → inflated `processed/total`; expected: only
  live work counted.

### Bug Condition F — Dropdown/collapsible break after navigation; janky animation (1.11, 1.12, 1.13)

`DOMContentLoaded` calls the `init*()` functions in one unguarded sequence; one throw leaves later
handlers (including the tools dropdown) unwired. `initCollapsible` measures `body.scrollHeight` (zero
when content is hidden/empty), mixes inline `maxHeight` with a `.collapsed { max-height:0 !important }`
class, and clears `maxHeight` via a fixed `350ms` `setTimeout` that overlaps on rapid toggles.
`genitractor.js`'s `initToolsDropdown` is missing the `menu` `stopPropagation` guard present in
`app.js`.

```
FUNCTION isBugCondition_ui(input)
  INPUT: input = {navigated: bool, an_earlier_init_threw: bool,
                  action in {"open_menu","toggle_collapsible","rapid_toggle"},
                  content_present: bool, page in {"chartporter","genitractor"}}
  OUTPUT: boolean
  RETURN (input.an_earlier_init_threw AND later_handlers_unwired())
      OR (input.action == "toggle_collapsible" AND NOT input.content_present AND relies_on_zero_scrollHeight())
      OR (input.action == "rapid_toggle" AND overlapping_timers())
      OR (input.page == "genitractor" AND input.action == "open_menu" AND missing_stopPropagation_guard())
END FUNCTION
```

### Bug Condition G — `NaN%` when `total == 0` (1.19)

The `artist_done` / `contact_done` handlers compute `Math.floor(100*ev.processed/ev.total)` with no
zero guard (unlike `renderItem`, which uses `Math.max(item.total,1)`).

```
FUNCTION isBugCondition_nan(input)
  INPUT: input = {event in {"artist_done","contact_done"}, total: int, processed: int}
  OUTPUT: boolean
  RETURN input.total == 0   // 100*p/0 -> NaN, rendered "NaN%"
END FUNCTION
```

### Bug Condition H — Race / concurrent I/O on Genitractor state and exports (1.14, 1.15)

`_geni_worker` mutates `item["status"|"processed"|"total"|"_contacts"]` outside `_geni_lock`, while
`api_cross_status` and `geni_export` read them under the lock. `api_export_all` selects items by
`output_path` existence only — including **running** items whose `.xlsx` is mid-write.

```
FUNCTION isBugCondition_race(input)
  INPUT: input = {concurrent_reader: bool, worker_running: bool, op in {"cross","export","export_all","merge"}}
  OUTPUT: boolean
  RETURN (input.worker_running AND input.concurrent_reader AND shared_fields_accessed_without_lock())
      OR (input.op IN {"export","export_all","merge"} AND reads_incomplete_or_running_output())
END FUNCTION
```

### Bug Condition I — Unbounded feed-log DOM growth (1.17)

Chartporter appends `.ablock` to `feed.log` and Genitractor appends `.ablock` to `#feeds-grid` with no
cap; only the system console trims to 200 lines.

```
FUNCTION isBugCondition_dom(input)
  INPUT: input = {rendered_blocks: int, container in {"feed.log","#feeds-grid"}}
  OUTPUT: boolean
  RETURN input.rendered_blocks > FEED_BLOCK_CAP AND NOT trimmed(input.container)
END FUNCTION
```

## Expected Behavior

The desired correct behavior for each bug condition is defined formally in the **Correctness
Properties** section (the single source of truth). This section records what must **stay unchanged**.

### Preservation Requirements

**Unchanged Behaviors (¬C inputs that must behave exactly as today):**
- A single, uninterrupted run with no navigation/refresh: timer increments correctly; `% TOTAL`,
  `% CLEAN`, `% FOUND` (and the click-to-toggle fraction view) read correctly (3.1, 3.5).
- Chartporter audit results: identical KEEP/REVIEW/DROP_* classification and status reasons; iTunes /
  Deezer / Chartmetric / labels / AI logic untouched (3.2).
- Export **columns and filters**: keep/review/drops/all, merge-all, and the Genitractor contacts
  export include the same columns and the same row-selection filters. Only the *container format*
  changes to CSV; the removal of workbook/cell styling is intentional and is NOT a regression (3.3).
- Unaffected modals/controls: API-key modal, feedback modal + Groq cleanup, STOP confirm, file upload,
  status pills, global filters behave exactly as today (3.4).
- Chartporter concurrency model: up to 4 concurrent items, 4 parallel artists each, incremental 25-row
  checkpoint writes (3.6).
- Genitractor normal-sized runs: Instagram/Facebook/Twitter extraction, display, and export unchanged
  (3.7).
- SSE semantics: queue items, feed blocks, and console lines render with the same event types and
  reconnect behavior; new fields are additive (3.8).
- Tools dropdown and collapsibles in a single normal session: navigate and show/hide as expected
  (3.9).

**Scope of ¬C:**
All inputs that are NOT a reconnect/refresh-mid-run, NOT a zero-total event, NOT a Genius error
response or large run, NOT a concurrent reader/exporter against a running worker, and NOT an
over-cap feed must be completely unaffected.

## Hypothesized Root Cause

Each root cause was confirmed by reading the source on `feat/catalog-audit-v5`.

### A. Timer (1.1, 1.2)
- `app/static/app.js` → `startTimer()`: `_timerStart=Date.now()` set only here; `startTimer()` is wired
  only to `#btn-run` in `DOMContentLoaded`. `handleEvent`'s `snapshot` branch rebuilds the queue/feeds
  but never restores a start time. `stopTimer()`/`checkAllDone()` are fine for a live session.
- `app/static/genitractor.js` → identical `startTimer()`/`_timerStart` pattern.
- `app/static/{app.js,genitractor.js}` → `initCrossToolBar()` writes `#ctb-fill` and `#ctb-stats` only;
  **nothing writes `#ctb-timer`** (present in both HTML files).
- `app/jobs.py` → `JobItem` has no start-time field and `to_dict()` omits one.
- `app/server.py` → `_geni_items` dicts have no start-time; `api_cross_status` returns no timing.

### B. Clear (1.3, 1.4)
- `app/static/index.html` queue-bar has ADD/RUN/STOP/EXPORT, **no CLEAR**. Backend
  `/api/queue/clear` → `JobManager.clear_done()` already exists and broadcasts a fresh snapshot.
- `app/static/genitractor.html` queue-bar likewise has no CLEAR, and `app/server.py` exposes **no**
  `/api/genitractor/clear` route; `_geni_items` / per-item `_contacts` are never reset.

### C. Export format + empty-state UX (1.5, 1.6, 1.20)
- `app/excel.py` → `write_xlsx()` applies `Font`/`PatternFill`/`Alignment`/`Border`, column widths,
  `freeze_panes`, `auto_filter`; `filter_xlsx_by_status()` and `merge_all_outputs()` re-emit via
  `write_xlsx()`. `app/jobs.py` → `_write_partial()` writes `{stem}Output.xlsx` every 25 rows.
- `app/server.py` → `/api/download`, `/api/export`, `/api/export_all`, `/api/stop_and_export` all
  `send_file(...xlsx)`; `/api/genitractor/export` already builds CSV correctly (good reference).
- Empty-state UX: `app/static/app.js` `dl()` reports failures via `sys(...,"bad")` (transient console).
  `app/static/genitractor.js` export handler uses `window.location.href="/api/genitractor/export"`, so
  a `404` JSON body replaces the page.
- Implication: `_genius_worker` in `server.py` re-opens item outputs with `openpyxl.load_workbook` to
  append socials. If checkpoints become CSV, that path must read/write CSV instead (see Design
  Decisions).

### D. Genius pacing (1.7, 1.16)
- `app/sources/genius.py` → `_MIN_INTERVAL = 0.5` (comment "2 req/sec"); `_geni_worker` comment says
  "0.25s between calls" — **inconsistent**. On `429`: one `time.sleep(2.0)` + retry, then return `None`
  (gives up). No detection of Cloudflare `1015` or `403` HTML bodies; non-JSON `raise_for_status()`/
  `.json()` failures are swallowed by the broad `except`.
- `app/server.py` → `_geni_worker` has no periodic pause; `_genius_lock` in `genius.py` only serializes
  request *timing*, it is **not** a pass-level mutex, so `_genius_worker` and `_geni_worker` can run
  concurrently.

### E. Stats accuracy (1.8, 1.9, 1.10, 1.18)
- `app/static/app.js` → `updateStats()` sums per-feed `counts` (client-only); `_totalArtists` is only
  `+=` on `item_started`. The `snapshot` branch clears `qState`/feeds and **does not** read the
  `processed/keep/review/drop/total` already present in `JobItem.to_dict()`.
- `app/static/genitractor.js` → `totalProcessed/totalArtists/totalFound` are client-accumulated;
  `_geni_item_dict()` exposes `processed/total` but **not** `found`.
- `app/server.py` → `api_cross_status` adds both `running` and `done` items into the totals
  (Chartporter branch explicitly, Genitractor branch unconditionally), inflating live counts (1.18).

### F. Init resilience / collapsible / animation (1.11, 1.12, 1.13)
- `app/static/{app.js,genitractor.js}` → `DOMContentLoaded` runs `init*()` in one unguarded sequence;
  an exception in an earlier init aborts the rest (the dropdown is wired late).
- `initCollapsible()` reads `body.scrollHeight` (0 when hidden/empty), toggles a `.collapsed` class
  whose CSS uses `max-height:0 !important`, while also assigning inline `style.maxHeight` — the
  `!important` and inline values fight. The expand path clears `maxHeight` on a `350ms` `setTimeout`
  that overlaps on rapid toggles.
- `genitractor.js` `initToolsDropdown()` lacks `menu.addEventListener("click", e=>e.stopPropagation())`
  (present in `app.js`), so a click inside the menu bubbles to the document handler that closes it.

### G. NaN guard (1.19)
- `app/static/app.js` `handleEvent` `artist_done` and `app/static/genitractor.js` `contact_done`
  compute `Math.floor(100*ev.processed/ev.total)` with no zero guard.

### H. Race / I/O (1.14, 1.15)
- `app/server.py` `_geni_worker` writes `item["status"|"processed"|"total"|"_contacts"]` outside
  `_geni_lock`; `api_cross_status` and `geni_export` read under the lock → torn reads.
- `api_export_all` selects items by `output_path.exists()` only, so a **running** item's mid-write
  `.xlsx` can be merged. `_write_partial` rewrites the same path repeatedly, so a concurrent reader can
  catch a partial file.

### I. DOM cap (1.17)
- `app/static/app.js` `addArtistToFeed` → `feed.log.append(block)` uncapped; `app/static/genitractor.js`
  `addContactToFeed` → `grid.append(block)` uncapped. Only `sys()` trims (`>200`).

## Correctness Properties

These numbered properties are the single source of truth for property-based and example tests.

Property 1: Bug Condition — Timer survives navigation/refresh and cross-tool timer ticks

_For any_ run where a server start timestamp `started_at` exists and the page is (re)loaded mid-run,
the fixed client SHALL render elapsed time computed as `now - started_at` on `#timer`, and SHALL
continuously update `#ctb-timer` from the running tool's `started_at` exposed via `/api/cross-status`.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — Single-session timer

_For any_ single uninterrupted session (no navigation/refresh), the fixed timer SHALL display the same
incrementing elapsed time as the original.

**Validates: Requirements 3.1**

Property 3: Bug Condition — Clear controls reset both queues

_For any_ queue state on either tool, invoking Clear SHALL clear the server queue (Chartporter via the
existing `/api/queue/clear`; Genitractor via a new endpoint that clears `_geni_items`/`_contacts` under
`_geni_lock`) and reset the associated client feed/stat state.

**Validates: Requirements 2.3, 2.4**

Property 4: Bug Condition — Plain-CSV exports

_For any_ export variant (Chartporter keep/review/drops/all, merge-all, and Genitractor contacts), the
fixed system SHALL return a `text/csv` response with a `.csv` filename whose body is a header row
followed by raw cell values with no workbook/cell formatting, using the **same columns and the same
row filters** as today.

**Validates: Requirements 2.20**

Property 5: Bug Condition — Export empty-state UX

_For any_ export request where no completed output exists, the fixed system SHALL present a clear,
persistent in-UI message (Chartporter) and SHALL NOT navigate the browser to a raw JSON page
(Genitractor); no silent no-op.

**Validates: Requirements 2.5, 2.6**

Property 6: Preservation — Export columns/filters

_For any_ export produced from completed outputs, the set of columns and the row-selection filter
results SHALL be identical to the original (only the container format changes to CSV).

**Validates: Requirements 3.3**

Property 7: Bug Condition — Genius backoff, pause, and reconciled interval

_For any_ Genius response in {429, Cloudflare 1015, 403-HTML}, the fixed code SHALL apply escalating
exponential backoff (not a single fixed retry), SHALL enforce a single documented minimum request
interval, and SHALL pause for a configured duration every N artists during a Genitractor run.

**Validates: Requirements 2.7**

Property 8: Bug Condition — Genius cross-pass mutual exclusion

_For any_ attempt to start a Genius-consuming pass while another is active, the fixed code SHALL
serialize them via a shared global lock so they never call Genius concurrently.

**Validates: Requirements 2.16**

Property 9: Bug Condition — Stats restored from server truth

_For any_ reconnect/refresh mid-run, the fixed client SHALL restore `processed/keep/review/drop/total`
(Chartporter) and `processed/total/found` (Genitractor) from the SSE snapshot so `% TOTAL`, `% CLEAN`,
and `% FOUND` are accurate.

**Validates: Requirements 2.8, 2.9, 2.10**

Property 10: Bug Condition — Cross-status counts only live work

_For any_ `/api/cross-status` read, the fixed aggregation SHALL sum only currently-running items,
excluding `done`/`stopped`/`error` items, so live percentages are not inflated.

**Validates: Requirements 2.18**

Property 11: Preservation — Single-session stats

_For any_ normal single-session run with no navigation/refresh, the fixed stats SHALL match the
original values, including the click-to-toggle fraction view.

**Validates: Requirements 3.5**

Property 12: Bug Condition — Resilient init, robust collapsible, menu guard

_For any_ page load where one `init*()` throws, the fixed code SHALL still wire every other feature
(each init wrapped in try/catch); collapsibles SHALL open/close correctly without depending on a zero
`scrollHeight` or mixing inline `maxHeight` with a `!important` class, and without overlapping-timer
artifacts; and `genitractor.js` SHALL include the same menu `stopPropagation` guard as `app.js`.

**Validates: Requirements 2.11, 2.12, 2.13**

Property 13: Preservation — UI in a normal session

_For any_ single normal session, the tools dropdown and collapsibles SHALL navigate and show/hide
exactly as today.

**Validates: Requirements 3.9**

Property 14: Bug Condition — Zero-total renders 0%

_For any_ `artist_done`/`contact_done` event (or other % computation) with `total == 0`, the fixed UI
SHALL render `0%` rather than `NaN%`.

**Validates: Requirements 2.19**

Property 15: Bug Condition — Synchronized Genitractor state and safe exports

_For any_ concurrent reader while a worker runs, the fixed code SHALL access shared Genitractor fields
only under `_geni_lock`; and _for any_ export/merge, it SHALL read only completed, fully-written
outputs (snapshot/copy or status-gated), with `export_all` excluding running items' partial outputs.

**Validates: Requirements 2.14, 2.15**

Property 16: Bug Condition — Bounded feed DOM

_For any_ run that renders more than the configured cap of feed blocks, the fixed client SHALL
trim oldest blocks (mirroring the 200-line console cap) to bound memory/rendering on both pages.

**Validates: Requirements 2.17**

Property 17: Preservation — Audit classification & SSE semantics

_For any_ audited artist, the fixed system SHALL produce the same KEEP/REVIEW/DROP_* classification and
status reasons, render the same queue/feed/console output under the same SSE event types, and preserve
the Chartporter concurrency model (4 items / 4 artists / 25-row checkpoints) and the unaffected modals.

**Validates: Requirements 3.2, 3.4, 3.6, 3.7, 3.8**

## Fix Implementation

### A. Timer (Properties 1, 2)
- **`app/jobs.py`**: add `started_at: Optional[float] = None` to `JobItem`; set
  `item.started_at = time.time()` in `_run_item()` at the `status="running"` transition; include
  `"started_at"` in `to_dict()`.
- **`app/server.py`**: in `geni_upload`/`_geni_worker`, add `started_at` to the item dict, set it when
  the worker flips to `running`; include it in `_geni_item_dict()`. Extend `api_cross_status` to return
  `started_at` (the min start of currently-running items) per tool.
- **`app/static/app.js` / `genitractor.js`**: replace `_timerStart` semantics with a server-provided
  epoch. On `snapshot`/`item_started`, if any item is `running`, set `_timerStart = started_at*1000`
  and start the interval; render `elapsed = now - started_at`. In `initCrossToolBar()`, when the other
  tool is running and `started_at` is present, write `#ctb-timer` each poll (and tick locally between
  polls). Keep `stopTimer()`/`checkAllDone()` for the idle transition.

### B. Clear (Property 3)
- **Chartporter** — add a `CLEAR` button to `index.html` queue-bar (placed after `EXPORT`, before the
  `.pill-divider`, matching the existing `.queue-row` layout). Wire it in `app.js` to
  `POST /api/queue/clear`; on success reset client state: clear `feeds`, `qState`, `_totalArtists`,
  per-feed counts, and re-`updateStats()`. Guard with the existing `showConfirm(...)` modal.
- **Genitractor** — add a new route `POST /api/genitractor/clear` in `server.py` that, under
  `_geni_lock`, removes non-running items and clears their `_contacts` (mirroring `clear_done`), then
  `_geni_broadcast` a fresh snapshot. Add a matching `CLEAR` button to `genitractor.html` and wire it in
  `genitractor.js` to reset `totalProcessed/totalArtists/totalFound`, `qState`, and `#feeds-grid`.

### C. Export as plain CSV + empty-state UX (Properties 4, 5, 6)
- **New `app/csv_export.py`** (or functions in `excel.py`) using the stdlib `csv` module:
  `write_csv(df, path)`, `filter_csv_by_status(src, dst, statuses)`, `merge_all_csv(paths, dst)` — header
  row + raw `str()` values, no styling, same columns and same filter semantics as the openpyxl versions
  (including the `ALL` and `DROP*`-prefix rules).
- **`app/jobs.py`** `_write_partial`: write `{stem}Output.csv` instead of `.xlsx` (checkpoints become
  CSV — see Design Decisions). Keep the 25-row checkpoint cadence unchanged.
- **`app/server.py`**: `/api/download`, `/api/export/<id>/<filter>`, `/api/export_all`,
  `/api/stop_and_export` serve CSV via `send_file`/`Response` with `mimetype="text/csv"` and `.csv`
  `download_name`. Update `_genius_worker` to read/append socials on the CSV (pandas read/concat +
  `write_csv`) instead of `openpyxl`.
- **Empty-state UX**: keep returning a JSON `{"error": ...}` with the existing status codes, but have
  the clients handle it in-UI. `app.js` `dl()` already parses the JSON error — additionally render a
  **persistent** banner/inline message (not just the scrolling `sys()` line). `genitractor.js`: replace
  `window.location.href=...` with a `fetch()`; on `ok` trigger a blob download, on error show a
  persistent in-UI message; the page never navigates to JSON.

### D. Genius pacing (Properties 7, 8)
- **`app/sources/genius.py`**: pick one documented interval — set `_MIN_INTERVAL = 0.5` (2 req/s) and
  fix the stale "0.25s" comment in `_geni_worker` to match. Replace the single-retry 429 block with an
  escalating backoff helper (e.g. delays `2,4,8,16,32`s, capped, with jitter) that also triggers on
  Cloudflare `1015` and `403` whose body is HTML (detect via status + `Content-Type`/body sniff). On
  exhaustion, surface a typed "rate-limited" outcome rather than silently returning `None`.
- **`app/server.py`** `_geni_worker`: add configurable `GENI_PAUSE_EVERY = 250` and
  `GENI_PAUSE_SECONDS = 5` (defaults) — sleep `GENI_PAUSE_SECONDS` every `GENI_PAUSE_EVERY` artists.
- Add a module-level `genius_pass_lock = threading.Lock()` shared by `_genius_worker` and `_geni_worker`;
  acquire it for the duration of each pass so the two never hammer Genius concurrently. (This is distinct
  from `genius._genius_lock`, which only paces individual request timing.)

### E. Stats from server truth (Properties 9, 10, 11)
- **`app/server.py`**: add a per-item `found` counter to the Genitractor item dict (increment in
  `_geni_worker` when a contact has any social) and expose it in `_geni_item_dict()`. Fix
  `api_cross_status` to sum **only** `status == "running"` items for both tools.
- **`app/static/app.js`**: in the `snapshot` branch, restore `_totalArtists` and per-feed `counts`
  (`keep/review/drop`) from each item's `processed/keep/review/drop/total`, then `updateStats()`.
- **`app/static/genitractor.js`**: in `snapshot`, restore `totalArtists/totalProcessed/totalFound` from
  the items' `total/processed/found`, then `updateStats()`.
- Live single-session math is unchanged, preserving Property 11.

### F. Init resilience / collapsible / animation (Properties 12, 13)
- **`app/static/app.js` & `genitractor.js`**: wrap each `init*()` call in `DOMContentLoaded` in its own
  `try/catch` (log to `sys(...,"bad")` on failure) so one failure cannot unwire the rest.
- Rewrite `initCollapsible()` to a robust CSS-driven mechanism: prefer animating
  `grid-template-rows: 1fr → 0fr` (or a measured `max-height` that does not rely on `scrollHeight` being
  non-zero), drive open/close entirely by a single class, and remove the inline-`maxHeight` +
  `!important` conflict and the `350ms` `setTimeout`. Update `styles.css`/`genitractor.css` accordingly
  (drop the `max-height:0 !important` rule in favor of the class-driven transition).
- Add the missing `menu.addEventListener("click", e=>e.stopPropagation())` to `genitractor.js`
  `initToolsDropdown()`.

### G. NaN guard (Property 14)
- **`app/static/app.js`** (`artist_done`) & **`genitractor.js`** (`contact_done`): compute percent via a
  helper `pct(p,t){ return t>0 ? Math.floor(100*p/t) : 0 }` and use it everywhere a `% ` is derived from
  `ev.total`.

### H. Race / safe I/O (Property 15)
- **`app/server.py`** `_geni_worker`: take `_geni_lock` around every mutation of
  `status/processed/total/_contacts` (short critical sections; do Genius I/O outside the lock, then lock
  to append the contact and bump counters).
- `geni_export`: copy `_contacts` under the lock (already does) and only include items whose
  `status != "running"`. `api_export_all`: select only items with `status in {"done","stopped"}` (and an
  existing output), excluding running items' partial outputs. For Chartporter CSV checkpoints, export
  reads a status-gated/copied file so it never reads a file mid-write.

### I. DOM cap (Property 16)
- **`app/static/app.js`** `addArtistToFeed`: after append, trim `feed.log` to a `FEED_BLOCK_CAP` (e.g.
  200) via `while(feed.log.children.length>FEED_BLOCK_CAP) feed.log.firstChild.remove()`.
- **`app/static/genitractor.js`** `addContactToFeed`: same trim on `#feeds-grid`.

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples on the **unfixed** code to confirm each root cause, then
verify the fix satisfies the bug-condition properties and preserves ¬C behavior. Because much of the
defect surface is front-end + server JSON contracts, "fix-check" and "preservation-check" are framed as
deterministic assertions on server responses/state and DOM behavior.

### Exploratory Bug Condition Checking

**Goal**: Demonstrate each bug before fixing; confirm/refute the root-cause analysis.

**Test Cases (expected to fail / reproduce on unfixed code):**
1. **Timer**: load `snapshot` with a running item → `#timer` stays `00:00`; assert `#ctb-timer` never
   changes during a cross-tool run.
2. **Clear**: assert no Clear control exists; assert `GET`/`POST /api/genitractor/clear` → 404.
3. **Export format**: hit `/api/export/<id>/keep` → response is `.xlsx` / openpyxl bytes (not `text/csv`).
4. **Export empty-state**: Genitractor export with no contacts → response is JSON and the browser would
   navigate to it; Chartporter export with no output → only a transient console line.
5. **Genius**: simulate repeated `429`/`1015` → code retries once then returns `None`; assert
   `_MIN_INTERVAL` (0.5) ≠ the "0.25s" comment; assert no pause and no cross-pass lock.
6. **Stats**: process N then replay `snapshot` → `_totalArtists`/feed counts reset; `% CLEAN`/`% FOUND`
   wrong. Cross-status with a `done` + a `running` item → inflated totals.
7. **UI**: force an early `init*()` to throw → dropdown unwired; toggle a collapsible with empty content
   → stuck (zero `scrollHeight`); rapid toggle → overlapping-timer jank; Genitractor menu click closes
   the menu (missing guard).
8. **NaN**: emit `artist_done`/`contact_done` with `total:0` → UI shows `NaN%`.
9. **Race/I/O**: hammer `/api/cross-status` while `_geni_worker` mutates fields → torn reads; run
   `export_all` while an item is mid-write → partial/corrupt merge.
10. **DOM**: stream thousands of blocks → DOM node count grows unbounded.

**Expected Counterexamples**: dead timers, 404 on geni clear, `.xlsx` bytes, JSON-page navigation,
give-up-after-one-retry, reset counters, inflated cross totals, unwired handlers, `NaN%`, torn reads,
unbounded DOM.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed code produces the expected behavior.

```
FOR ALL input WHERE isBugCondition_X(input) DO
  result := fixed_behavior(input)
  ASSERT expectedProperty_X(result)   // per Properties 1,3,4,5,7,8,9,10,12,14,15,16
END FOR
```

Examples: snapshot-with-running → `#timer`/`#ctb-timer` show `now-started_at`; every export endpoint →
`text/csv` + `.csv` + header+rows with identical columns/filters; 429/1015/403-HTML → escalating
backoff + eventual completion; reconnect → restored counts; `total==0` → `0%`; concurrent reader →
consistent fields; over-cap feed → trimmed.

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, the fixed code equals the original.

```
FOR ALL input WHERE NOT isBugCondition_X(input) DO
  ASSERT original_behavior(input) == fixed_behavior(input)   // per Properties 2,6,11,13,17
END FOR
```

**Approach**: Property-based testing is preferred for preservation because it generates many ¬C inputs
and catches edge cases. Capture baseline behavior on the **unfixed** code first, then assert equality
after the fix.

**Test Cases**:
1. **Audit equivalence**: golden CSV → identical Status/Status Reason/labels columns before vs after
   (Property 17, 3.2).
2. **Export columns/filters**: for the same completed dataset, the CSV column set and the per-filter row
   sets equal the rows the `.xlsx` path would have produced (Property 6, 3.3).
3. **Single-session timer/stats**: no navigation → timer and `% TOTAL`/`% CLEAN`/`% FOUND` (and toggle)
   match original (Properties 2, 11; 3.1, 3.5).
4. **Modals/UI normal session**: API-key/feedback/STOP/upload/pills/filters and dropdown/collapsibles
   behave as today (Properties 13, 17; 3.4, 3.9).
5. **Concurrency model**: 4 items / 4 artists / 25-row checkpoints unchanged (3.6).

### Unit Tests
- CSV writer/filter/merge: header + raw values, no styling; `ALL` and `DROP*` filter rules; column
  parity with `excel.py`.
- Genius backoff helper: delay schedule for 429/1015/403-HTML; interval reconciliation.
- `api_cross_status`: running-only aggregation; `started_at` surfaced.
- `pct(p,t)` helper: `t==0 → 0`.
- Genitractor clear endpoint: clears items/`_contacts` under lock; broadcasts snapshot.

### Property-Based Tests
- Generate random item count/status mixes → cross-status sums only running items (Property 10).
- Generate random `processed/keep/review/drop/total` snapshots → restored client stats equal server
  truth; never `NaN` (Properties 9, 14).
- Generate random export datasets → CSV row/column sets equal the filtered source for every variant
  (Properties 4, 6).
- Generate interleaved reader/writer schedules on Genitractor state → no torn reads (Property 15).
- Generate large block streams → DOM stays ≤ cap (Property 16).

### Integration Tests
- Start run → refresh mid-run → timer resumes and `%` accurate; finish → idle timer stops.
- Cross-tool: run on tool A, open tool B → `#ctb-timer` ticks, cross bar reflects only live work.
- Full export flow per variant → downloaded `.csv` opens with correct header + rows; empty-state shows
  persistent in-UI message with no page navigation.
- Genitractor + Genius social pass started together → serialized via the shared pass lock.
- Clear on both tools → server queue and client feed/stat state reset.

## Design Decisions & Trade-offs

- **Server as source of truth for time and counts.** Rather than persisting client timer/counters
  across reloads (fragile), we add `started_at` and already-present counts to the SSE `snapshot` and
  `/api/cross-status`. New fields are **additive**, preserving SSE semantics (3.8). Trade-off: slightly
  larger payloads; negligible.
- **Checkpoints become CSV too.** Since exports are CSV and `_write_partial` is the source for
  downloads, writing checkpoints directly as CSV avoids a dual-format path and an xlsx→csv conversion
  step. Consequence: `_genius_worker` must read/append socials on CSV (pandas) instead of openpyxl. We
  keep the 25-row cadence and concurrency model unchanged (3.6). Alternative considered (keep xlsx
  checkpoints, convert on export) was rejected as it retains the openpyxl dependency on the hot path and
  complicates the "read only completed output" guarantee.
- **`excel.py` retained but off the export path.** We add CSV functions rather than deleting
  `excel.py`, minimizing blast radius; openpyxl simply stops being used for exports/checkpoints. The
  removal of all cell/workbook styling is intentional per 2.20 and is explicitly **not** a regression
  (3.3).
- **Empty-state stays JSON on the wire, in-UI on screen.** We keep the existing JSON error contract
  (so API behavior/status codes are stable) and change only how clients present it — Genitractor stops
  navigating to the JSON page; both tools show a persistent message. This preserves 3.4/3.8 while fixing
  2.5/2.6.
- **Two distinct Genius locks.** `genius._genius_lock` continues to pace individual request *timing*; a
  new pass-level `genius_pass_lock` provides mutual exclusion between the two passes (2.16). Conflating
  them would either over-serialize individual calls or fail to prevent concurrent passes.
- **Interval choice.** We standardize on `0.5s` (2 req/s), the value already tested in code, and correct
  the misleading "0.25s" comment, favoring the safer documented value (2.7).
- **Collapsible mechanism.** Prefer `grid-template-rows` (or measured max-height) over `scrollHeight`,
  driven by a single class with no `!important`/inline conflict and no overlapping timers — robust when
  content is empty and performant on rapid toggles (2.12, 2.13).
- **Feed cap = 200** to mirror the existing console cap for consistency; configurable constant so it can
  be tuned without code changes elsewhere.

## Explicitly Unchanged (Out of Scope — clauses 3.x)

The following MUST remain unchanged and are not touched except where a fix is strictly additive:
- **Audit/classification logic** — `app/audit.py`, label logic, iTunes/Deezer/Chartmetric evaluation,
  KEEP/REVIEW/DROP_* statuses and reasons (3.2).
- **Unaffected modals/controls** — API-key modal, feedback modal + Groq cleanup, STOP confirm, file
  upload, status pills, global filters (3.4).
- **SSE event semantics and reconnect behavior** — event types and rendering contracts; new fields are
  additive only (3.8).
- **Chartporter concurrency model** — up to 4 concurrent items, 4 parallel artists each, incremental
  25-row checkpoint writes (3.6).
- **Export columns and filters** — identical columns and filter results across keep/review/drops/all,
  merge-all, and Genitractor contacts; only the container format changes to CSV (3.3).
- **Genitractor normal-run extraction/display/export** of Instagram/Facebook/Twitter (3.7).
