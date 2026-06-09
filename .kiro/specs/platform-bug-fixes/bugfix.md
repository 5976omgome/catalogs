# Bugfix Requirements Document

## Introduction

This bugfix spec covers a critical, whole-platform review of the **catalogs** platform — the Flask
application running out of `app/` (entry point `run.py` → `app/server.py`). The platform ships two
tools that share one server process and one SSE/job backbone:

- **Chartporter** — `app/static/index.html` + `app/static/app.js` (catalog ownership audit).
- **Genitractor** — `app/static/genitractor.html` + `app/static/genitractor.js` (Genius contact extraction).

Both tools share `app/server.py`, `app/jobs.py`, `app/sources/*`, `app/cache.py`, `app/excel.py`,
`app/keys.py`, and `app/config.py`.

The work is targeted at the running app under `app/`, on branch **`feat/catalog-audit-v5`** (currently
checked out). The investigation read the actual source files to confirm each defect; the bug conditions
below describe observable, reproducible behavior. The corresponding root-cause-in-code analysis and the
concrete fix-check / preservation-check implementation details belong in the **design** phase and will be
captured in `design.md`.

This document uses the **bug condition methodology**. Each defect is expressed as an observable bug
condition `C(X)` (Current Behavior), a desired property for that same condition (Expected Behavior), and a
set of inputs `¬C(X)` whose behavior must be preserved (Unchanged Behavior / Regression Prevention).

The seven user-reported/confirmed bugs are captured as clauses 1.1–1.13. Additional confirmed defects found
during the platform-wide scan (race conditions, concurrent file I/O, unbounded growth, miscounting, and
divide-by-zero) are captured as clauses 1.14–1.19. The export output-format defect (styled `.xlsx` instead
of plain CSV) is captured as clause 1.20.

## Bug Analysis

### Current Behavior (Defect)

**Elapsed timer freeze on navigation/refresh**

*C(X): a job is running and the user switches tools or refreshes the page.*

1.1 WHEN a job is running and the user navigates between Chartporter and Genitractor (or refreshes the page) THEN the queue-bar timer (`#timer`) resets to `00:00` and stays dead, because elapsed time is tracked only client-side (`_timerStart`/`_timerInterval`) and is only initialized on the RUN click, with no server-side job start timestamp to restore from.

1.2 WHEN a job is running on the other tool and the cross-tool progress bar is visible THEN the cross-tool elapsed timer (`#ctb-timer`) remains stuck at `00:00` for the entire run, because no code path ever updates that element.

**No Clear control on either queue**

*C(X): the user wants to clear/reset a queue of finished or stale items.*

1.3 WHEN the Chartporter queue contains finished, stopped, or errored items THEN there is no control in the UI to clear/reset the queue, even though a backend clear path exists, leaving the user unable to reset queue/feed/stat state.

1.4 WHEN the Genitractor queue contains finished, stopped, or errored items THEN there is no control to clear the queue AND no backend endpoint exists to clear Genitractor queued/finished items, so contacts and queue items accumulate for the lifetime of the server process.

**Export popup does not produce a file**

*C(X): the user presses EXPORT and confirms YES.*

1.5 WHEN the user presses EXPORT on Chartporter and confirms YES before any item has produced output (or when only partial/in-progress output exists) THEN no file is delivered and the failure is surfaced only as a transient system-console line, so the export "popup" appears to do nothing.

1.6 WHEN the user presses EXPORT on Genitractor and confirms YES THEN under conditions where no contacts have been collected the action navigates to a raw JSON error instead of downloading a file, so the export "popup" appears broken.

**Genitractor runs too fast and errors out at scale**

*C(X): a Genitractor run contains thousands of artists (~4000+).*

1.7 WHEN a Genitractor run processes thousands of artists THEN it issues Genius API requests faster than the service tolerates and, on hitting repeated `429`/Cloudflare `1015` responses, it does not pause or back off — it keeps issuing requests, swallows the error responses, and the run fails/stalls without completing.

**Inaccurate progress / found percentages**

*C(X): stats are read after any SSE reconnect, page switch, or refresh during a run.*

1.8 WHEN Chartporter stats (`% CLEAN`) are read after a page switch, refresh, or SSE reconnect during a run THEN the displayed percentage is wrong, because the clean/processed counters are accumulated purely from client-side SSE deltas and the snapshot on reconnect rebuilds feeds empty without restoring server-truth counts.

1.9 WHEN Genitractor stats (`% FOUND`) are read after a page switch, refresh, or SSE reconnect during a run THEN the displayed percentage is wrong, because `totalProcessed`/`totalArtists`/`totalFound` are client-accumulated and are not restored from the server snapshot.

1.10 WHEN the `% TOTAL` stat is read after a refresh/reconnect mid-run on either tool THEN it desyncs (processed count and total no longer correspond), because `_totalArtists`/`totalArtists` are only incremented on `item_started` events and are lost on reload.

**System dropdown and collapsibles unresponsive after navigation**

*C(X): the user opens the tools dropdown or toggles a collapsible card after switching pages.*

1.11 WHEN the user clicks the SYSTEM/tools dropdown (`#tool-btn` / `#tools-menu`) after navigating between the tools THEN it can fail to open/respond, because the dropdown handlers are registered late in a single unguarded `DOMContentLoaded` init sequence and any earlier init failure leaves later handlers unwired.

1.12 WHEN the user toggles a collapsible card (`.card-head[data-collapse]`) — especially before content exists — THEN the expand/collapse misbehaves or becomes stuck, because the toggle relies on `body.scrollHeight` (which is `0` when content starts hidden/empty) and mixes an inline `maxHeight` mechanism with a `.collapsed` CSS class that uses `!important`.

**Laggy / "butchered" dropdown and collapsible animations**

*C(X): the user opens/closes the tools menu or a collapsible card.*

1.13 WHEN the user opens/closes the tools menu or a collapsible card THEN the animation is janky, because the collapsible sets `maxHeight` to `scrollHeight` and clears it via a fixed `350ms` `setTimeout` (overlapping timers on rapid toggles) and the menu open/close has no measured, performant transition.

**Additional confirmed defects (platform-wide scan)**

1.14 WHEN the Genitractor cross-status endpoint or export reads item fields while a worker is running THEN it can read inconsistent state, because the worker mutates shared item dicts (`status`, `processed`, `total`, `_contacts`) without holding `_geni_lock` while readers access them under the lock.

1.15 WHEN an export/merge runs while a job is still writing incremental output THEN it can read partially-written or in-progress `.xlsx` files (and `export_all` includes running items' partial outputs), risking incomplete or corrupt exports.

1.16 WHEN the Genius social pass and a Genitractor run are active at the same time THEN their combined request rate exceeds the safe Genius limit, because there is no mutual exclusion between the two Genius-consuming code paths, increasing ban risk.

1.17 WHEN a run processes thousands of artists THEN the feed log DOM grows without bound (artist/contact blocks are appended with no cap, unlike the 200-line system console), degrading memory and rendering performance.

1.18 WHEN the cross-tool progress bar reads Genitractor status THEN its totals are inflated/incorrect, because the cross-status aggregation adds totals from non-running (done) items into the live counts.

1.19 WHEN a progress percentage is computed for an item whose `total` is `0` THEN the UI shows `NaN%`, because the `artist_done`/`contact_done` handlers divide by `ev.total` without guarding against zero.

**Exports are produced as styled `.xlsx` instead of plain CSV**

*C(X): the user exports from Chartporter (any variant) or Genitractor.*

1.20 WHEN the user exports any Chartporter variant (keep/review/drops/all or merge-all) THEN the system produces styled/formatted `.xlsx` workbooks (built via `app/excel.py` using openpyxl, applying cell styling, fonts, colors, column widths, and frozen panes) rather than plain `.csv` files containing only the raw data values.

### Expected Behavior (Correct)

2.1 WHEN a job is running and the user navigates between tools or refreshes THEN the system SHALL restore and continue the queue-bar timer from a server-provided job start timestamp so elapsed time survives navigation and refresh.

2.2 WHEN a job is running on the other tool and the cross-tool progress bar is visible THEN the system SHALL display and continuously update the cross-tool elapsed timer (`#ctb-timer`) from the server-provided job start time.

2.3 WHEN the Chartporter queue contains items THEN the system SHALL provide a Clear control that clears the queue and resets the associated client feed/stat state.

2.4 WHEN the Genitractor queue contains items THEN the system SHALL provide a Clear control backed by an endpoint that clears Genitractor queued/finished items and resets client state.

2.5 WHEN the user presses EXPORT on Chartporter and confirms YES THEN the system SHALL either deliver a valid export file or present a clear, persistent in-UI message explaining why no export is available (e.g., no completed outputs), without silently doing nothing.

2.6 WHEN the user presses EXPORT on Genitractor and confirms YES THEN the system SHALL deliver a valid contacts file when contacts exist and present a clear in-UI message (not a raw JSON page) when none exist.

2.7 WHEN a Genitractor run processes thousands of artists THEN the system SHALL throttle Genius requests within safe limits, pause/back off after a configurable number of artists, and gracefully handle `429`/`1015` responses (escalating backoff rather than continuing to hammer) so a large run completes without being banned.

2.8 WHEN Chartporter stats (`% CLEAN`) are read after a page switch, refresh, or reconnect during a run THEN the system SHALL show accurate values sourced from server-truth counts restored via the snapshot.

2.9 WHEN Genitractor stats (`% FOUND`) are read after a page switch, refresh, or reconnect during a run THEN the system SHALL show accurate values sourced from server-truth counts restored via the snapshot.

2.10 WHEN the `% TOTAL` stat is read after a refresh/reconnect mid-run on either tool THEN the system SHALL show a processed/total pair that stays consistent because both are restored from server truth.

2.11 WHEN the user clicks the tools dropdown after navigating between tools THEN the system SHALL open/close it reliably, with init wiring resilient to individual init failures.

2.12 WHEN the user toggles a collapsible card (including before content exists) THEN the system SHALL expand/collapse correctly and remain toggleable, without depending on a zero `scrollHeight` or conflicting inline/`!important` height rules.

2.13 WHEN the user opens/closes the tools menu or a collapsible card THEN the system SHALL animate smoothly and performantly, without overlapping-timer artifacts.

2.14 WHEN cross-status or export reads Genitractor item fields THEN the system SHALL read consistent state by synchronizing all reads and writes of shared item data.

2.15 WHEN an export/merge runs THEN the system SHALL operate only on completed, fully-written outputs (or safely-snapshotted copies) so exports cannot read partial/in-progress files.

2.16 WHEN a Genius-consuming pass is requested while another is active THEN the system SHALL serialize them (mutual exclusion) so the combined Genius request rate stays within safe limits.

2.17 WHEN a run processes thousands of artists THEN the system SHALL bound feed-log DOM growth (e.g., cap/trim rendered blocks) to keep memory and rendering performant.

2.18 WHEN the cross-tool progress bar reads status THEN the system SHALL report live counts that reflect only the currently running work, without inflating totals from finished items.

2.19 WHEN a progress percentage is computed for an item whose `total` is `0` THEN the system SHALL display `0%` (or a safe placeholder) rather than `NaN%`.

2.20 WHEN the user exports any Chartporter variant (keep/review/drops/all or merge-all) or the Genitractor contacts export THEN the system SHALL produce plain `.csv` files that contain only cell values (a header row followed by data rows), with no workbook or cell formatting of any kind (no colors, fonts, column widths, frozen panes, or other cell styling), and SHALL serve the download as `text/csv` with a `.csv` filename.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a job is running and the timer is active in a single uninterrupted session THEN the system SHALL CONTINUE TO display correct, incrementing elapsed time as it does today.

3.2 WHEN an artist is audited by Chartporter THEN the system SHALL CONTINUE TO produce the same KEEP/REVIEW/DROP_* classification and status reasons (audit, labels, iTunes/Deezer/Chartmetric logic unchanged).

3.3 WHEN an export is produced with completed outputs THEN the system SHALL CONTINUE TO include the same columns and the same export filters (keep/review/drops/all, merge-all, and the Genitractor contacts export), while the output format is intentionally changed to plain CSV — workbook/cell formatting (colors, fonts, column widths, frozen panes, cell styling) is deliberately removed per clause 2.20 and its absence is NOT a regression.

3.4 WHEN the user interacts with non-affected modals and controls (API key modal, feedback modal/submission, STOP confirm, file upload, status pills, global filters) THEN the system SHALL CONTINUE TO behave exactly as today.

3.5 WHEN stats are viewed during a normal single-session run with no navigation/refresh THEN the system SHALL CONTINUE TO show the same accurate `% TOTAL`, `% CLEAN`, and `% FOUND` values, including the click-to-toggle fraction view.

3.6 WHEN multiple CSVs are queued on Chartporter THEN the system SHALL CONTINUE TO process them with the existing concurrency model (up to 4 concurrent items, 4 parallel artists each) and incremental 25-row checkpoint writes.

3.7 WHEN Genitractor processes a normal-sized list and contacts are found THEN the system SHALL CONTINUE TO extract and display Instagram/Facebook/Twitter results and export them unchanged.

3.8 WHEN the SSE streams deliver events for live progress THEN the system SHALL CONTINUE TO render queue items, feed blocks, and system-console lines with the same event semantics and reconnect behavior.

3.9 WHEN the tools dropdown and collapsible cards are used in a single normal session THEN the system SHALL CONTINUE TO navigate between tools and show/hide card bodies as expected.
