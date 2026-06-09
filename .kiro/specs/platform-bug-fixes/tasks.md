# Implementation Plan

This plan fixes the 20 confirmed defects (clauses 1.1–1.20 / expected 2.x / preserved 3.x) across the
ten concern-areas A–I defined in `design.md`. It follows the exploratory bugfix methodology:

1. **Explore** (Task 1) — write a property-based exploration test that FAILS on the unfixed code,
   surfacing counterexamples for every concern-area.
2. **Preserve** (Task 2) — capture baseline behavior for ¬C inputs (audit, export columns/filters,
   single-session timer/stats, modals, concurrency) and verify those tests PASS on unfixed code.
3. **Implement** (Tasks 3–13) — apply fixes ordered so shared/backend foundations land before the
   client code that depends on them, and the CSV writer lands before the export UI/empty-state wiring.
4. **Validate** (Task 14) — full platform regression confirming fix-checks pass and all preservation
   requirements hold.

> Citation key used in annotations:
> `_Requirements:_` → bugfix.md clauses (2.x bug-fix / 3.x preservation).
> `_Correctness_Properties:_` → numbered Properties 1–17 in design.md ("Correctness Properties").
> `_Bug_Condition:_` / `_Expected_Behavior:_` / `_Preservation:_` → design.md `isBugCondition_*` and
> Preservation Requirements.

---

- [ ] 1. Write platform-wide bug-condition exploration test
  - **Property 1: Bug Condition** - Platform Defect Counterexamples (A–I)
  - **CRITICAL**: This test MUST FAIL on unfixed `feat/catalog-audit-v5` — failure confirms the bugs exist
  - **DO NOT attempt to fix the test or the code when it fails** — the goal is to surface counterexamples
  - **NOTE**: This suite encodes the expected behavior; it will validate the fixes when it passes after implementation
  - **Scoped PBT Approach**: for deterministic defects, scope each property to the concrete failing case(s) for reproducibility; use generated inputs where the property is genuinely universal (cross-status mixes, snapshot count restore, zero-total events, reader/writer interleavings, large block streams)
  - Encode one case per concern-area, mirroring design.md *Exploratory Bug Condition Checking* cases 1–10:
    - **A timer** (`isBugCondition_timer`): load an SSE `snapshot` carrying a `running` item → assert `#timer` stays `00:00`; assert `#ctb-timer` never changes during a cross-tool run. _Correctness_Properties: 1_ · _Requirements: 1.1, 1.2_
    - **B clear** (`isBugCondition_clear`): assert no Clear control exists on either queue-bar; assert `POST /api/genitractor/clear` → 404. _Correctness_Properties: 3_ · _Requirements: 1.3, 1.4_
    - **C export format** (`isBugCondition_export`): `GET /api/export/<id>/keep` → response is `.xlsx`/openpyxl bytes, not `text/csv`. _Correctness_Properties: 4_ · _Requirements: 1.20_
    - **C empty-state**: Genitractor export with no contacts → JSON page navigation; Chartporter export with no completed output → only a transient `sys()` console line. _Correctness_Properties: 5_ · _Requirements: 1.5, 1.6_
    - **D Genius** (`isBugCondition_genius`): simulate repeated `429`/`1015`/`403`-HTML → code retries once then returns `None`; assert `_MIN_INTERVAL`(0.5) ≠ "0.25s" comment; assert no pause-every-N and no cross-pass mutex. _Correctness_Properties: 7, 8_ · _Requirements: 1.7, 1.16_
    - **E stats** (`isBugCondition_stats`): process N then replay `snapshot` → `_totalArtists`/feed counts reset, `% CLEAN`/`% FOUND` wrong; `/api/cross-status` with a `done` + a `running` item → inflated totals. _Correctness_Properties: 9, 10_ · _Requirements: 1.8, 1.9, 1.10, 1.18_
    - **F ui** (`isBugCondition_ui`): force an early `init*()` to throw → tools dropdown unwired; toggle a collapsible with empty content → stuck (zero `scrollHeight`); rapid toggle → overlapping-timer jank; Genitractor menu click closes the menu (missing `stopPropagation`). _Correctness_Properties: 12_ · _Requirements: 1.11, 1.12, 1.13_
    - **G nan** (`isBugCondition_nan`): emit `artist_done`/`contact_done` with `total:0` → UI shows `NaN%`. _Correctness_Properties: 14_ · _Requirements: 1.19_
    - **H race** (`isBugCondition_race`): hammer `/api/cross-status` while `_geni_worker` mutates `status/processed/total/_contacts` → torn reads; run `export_all` while an item is mid-write → partial/corrupt merge. _Correctness_Properties: 15_ · _Requirements: 1.14, 1.15_
    - **I dom** (`isBugCondition_dom`): stream thousands of blocks into `feed.log` / `#feeds-grid` → DOM node count grows unbounded. _Correctness_Properties: 16_ · _Requirements: 1.17_
  - Run the suite on UNFIXED code
  - **EXPECTED OUTCOME**: every case FAILS/reproduces (dead timers, 404 on geni clear, `.xlsx` bytes, JSON-page navigation, give-up-after-one-retry, reset counters, inflated cross totals, unwired handlers, `NaN%`, torn reads, unbounded DOM)
  - Document the concrete counterexample for each area to confirm the root-cause analysis
  - Mark complete when the suite is written, run, and every failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20_

- [ ] 2. Write preservation baseline tests (BEFORE implementing any fix)
  - **Property 2: Preservation** - Unchanged Behaviors (¬C inputs)
  - **IMPORTANT**: Follow the observation-first methodology — record behavior on UNFIXED code, then assert it
  - Property-based testing is preferred here so many ¬C inputs are exercised; capture the baseline first, assert equality after the fix
  - Mirror design.md *Preservation Checking* cases 1–5:
    - **Audit equivalence**: run a golden CSV through `app/audit.py` → record identical `Status` / `Status Reason` / labels columns (no navigation/reconnect involved). _Correctness_Properties: 17_ · _Requirements: 3.2_
    - **Export columns/filters**: for a fixed completed dataset, record the column set and the per-filter row sets (keep/review/drops/all, merge-all, Genitractor contacts) produced by the current `.xlsx` path — these become the parity oracle for CSV. _Correctness_Properties: 6_ · _Requirements: 3.3_
    - **Single-session timer/stats**: a single uninterrupted run (no navigation/refresh) → record incrementing timer and `% TOTAL`/`% CLEAN`/`% FOUND` including the click-to-toggle fraction view. _Correctness_Properties: 2, 11_ · _Requirements: 3.1, 3.5_
    - **Modals/UI normal session**: API-key modal, feedback modal + Groq cleanup, STOP confirm, file upload, status pills, global filters, dropdown + collapsibles in one session → record current behavior. _Correctness_Properties: 13, 17_ · _Requirements: 3.4, 3.9_
    - **Concurrency model**: Chartporter run → record up-to-4 concurrent items, 4 parallel artists each, 25-row incremental checkpoint writes; Genitractor normal-sized run → record Instagram/Facebook/Twitter extraction/display/export. _Correctness_Properties: 17_ · _Requirements: 3.6, 3.7, 3.8_
  - Run on UNFIXED code
  - **EXPECTED OUTCOME**: all baseline tests PASS (this is the behavior to preserve)
  - Mark complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

---

## Backend foundations (land first — client code depends on these)

- [ ] 3. Backend foundation — server run-start time + Genitractor lock discipline (Concern A backend, Concern H locking)
  - This unblocks the client timer (Task 6) and makes all shared Genitractor reads consistent (Tasks 4, 5, 10)

  - [ ] 3.1 Add server-truth `started_at` to Chartporter jobs
    - `app/jobs.py`: add `started_at: Optional[float] = None` to `JobItem`; set `item.started_at = time.time()` in `_run_item()` at the `status="running"` transition; add `"started_at"` to `JobItem.to_dict()`
    - New field is additive to the SSE `snapshot`/event payload (no event-type changes)
    - _Bug_Condition: isBugCondition_timer (run_active AND navigated_or_refreshed)_
    - _Expected_Behavior: snapshot carries a server start timestamp to restore from_
    - _Correctness_Properties: 1_
    - _Requirements: 2.1_

  - [ ] 3.2 Add server-truth `started_at` to Genitractor items
    - `app/server.py`: add `started_at` to the `_geni_items` item dict; set it in `_geni_worker` when the worker flips to `running`; include it in `_geni_item_dict()`
    - _Bug_Condition: isBugCondition_timer (#ctb-timer never updated)_
    - _Correctness_Properties: 1_
    - _Requirements: 2.1, 2.2_

  - [ ] 3.3 Route all shared Genitractor field mutations through `_geni_lock`
    - `app/server.py` `_geni_worker`: take `_geni_lock` around every write of `status` / `processed` / `total` / `_contacts` (do Genius I/O outside the lock; lock only to append the contact and bump counters — short critical sections)
    - **Preservation check**: confirm the existing concurrency model is untouched — Genitractor worker throughput and event emission order unchanged; only mutation visibility is synchronized
    - _Bug_Condition: isBugCondition_race (worker_running AND concurrent_reader AND shared_fields_accessed_without_lock)_
    - _Expected_Behavior: readers under `_geni_lock` observe consistent state_
    - _Correctness_Properties: 15_
    - _Requirements: 2.14_

  - [ ] 3.4 Verify foundation reads are consistent (re-run Concern A/H exploration cases)
    - **Property 1: Expected Behavior** - started_at present and reads are torn-free
    - **IMPORTANT**: re-run the SAME A-timer (server payload) and H-race cases from Task 1 — do NOT write new tests
    - Assert `to_dict()` / `_geni_item_dict()` expose `started_at`; assert the interleaved reader/writer schedule no longer produces torn reads
    - **EXPECTED OUTCOME**: these cases now pass
    - _Correctness_Properties: 1, 15_
    - _Requirements: 2.1, 2.2, 2.14_

- [ ] 4. Backend foundation — server-truth counts + cross-status running-only (Concern E backend, Concern H/1.18 read)
  - Depends on Task 3 (lock discipline). Unblocks client stats restore (Task 7) and client timer cross-bar (Task 6)

  - [ ] 4.1 Expose a per-item `found` counter for Genitractor
    - `app/server.py`: increment a per-item `found` in `_geni_worker` (under `_geni_lock`) whenever an extracted contact has any social; expose `found` in `_geni_item_dict()`
    - _Bug_Condition: isBugCondition_stats (reconnected_midrun AND %FOUND counts_not_restored)_
    - _Correctness_Properties: 9_
    - _Requirements: 2.9_

  - [ ] 4.2 Fix `api_cross_status` to count only live work and surface `started_at`
    - `app/server.py` `api_cross_status`: sum **only** `status == "running"` items for BOTH the Chartporter and Genitractor branches (stop adding `done`/`stopped`/`error` items); return `started_at` per tool as the min start of currently-running items
    - **Preservation check**: cross-status payload stays additive — existing consumers still read the same keys; a single-session live run reports the same numbers it does today
    - _Bug_Condition: isBugCondition_stats (surface == "cross" AND cross_status_includes_done_items)_
    - _Expected_Behavior: live counts reflect only running items_
    - _Correctness_Properties: 1, 10_
    - _Requirements: 2.18, 2.2_

  - [ ] 4.3 Verify counts/cross-status (re-run Concern E exploration cases + PBT)
    - **Property 1: Expected Behavior** - cross-status sums running-only; `found` exposed
    - Re-run the E-stats cross-status case from Task 1; add the PBT from Testing Strategy: generate random item count/status mixes → `/api/cross-status` sums only running items
    - **EXPECTED OUTCOME**: inflated-totals case now passes; running-only property holds for all generated mixes
    - _Correctness_Properties: 10_
    - _Requirements: 2.9, 2.18_

- [ ] 5. Backend foundation — CSV export rewrite (Concern C backend, Concern H export safety)
  - **Do this BEFORE wiring export UI/empty-state (Task 9).** Depends on Task 3 (lock) for safe reads

  - [ ] 5.1 Add a stdlib-`csv` export module
    - New `app/csv_export.py` (or new functions in `app/excel.py`): `write_csv(df, path)`, `filter_csv_by_status(src, dst, statuses)`, `merge_all_csv(paths, dst)` — header row + raw `str()` values, NO styling, replicating the exact columns and the exact filter semantics of the openpyxl versions (including the `ALL` rule and the `DROP*`-prefix matching)
    - **Preservation check**: column set and per-filter row selection MUST equal `excel.py`'s output — assert against the parity oracle recorded in Task 2
    - _Bug_Condition: isBugCondition_export (output_format == "xlsx_styled")_
    - _Expected_Behavior: plain CSV, header + raw values, same columns/filters_
    - _Correctness_Properties: 4, 6_
    - _Requirements: 2.20, 3.3_

  - [ ] 5.2 Switch incremental checkpoints to CSV
    - `app/jobs.py` `_write_partial`: write `{stem}Output.csv` instead of `.xlsx`; keep the 25-row checkpoint cadence and concurrency model unchanged
    - **Preservation check**: checkpoint timing/cadence (every 25 rows) and the 4-item/4-artist model unchanged — only the on-disk format changes
    - _Correctness_Properties: 4, 17_
    - _Requirements: 2.20, 3.6_

  - [ ] 5.3 Serve all Chartporter downloads/exports as `text/csv`
    - `app/server.py`: `/api/download`, `/api/export/<id>/<filter>`, `/api/export_all`, `/api/stop_and_export` serve CSV via `send_file`/`Response` with `mimetype="text/csv"` and a `.csv` `download_name`
    - _Bug_Condition: isBugCondition_export (output_format == "xlsx_styled")_
    - _Correctness_Properties: 4_
    - _Requirements: 2.20_

  - [ ] 5.4 Update `_genius_worker` to read/append socials on CSV
    - `app/server.py` `_genius_worker`: replace `openpyxl.load_workbook` append path with pandas read/concat + `write_csv` so the post-audit social pass operates on the CSV checkpoints
    - **Preservation check**: the socials appended and resulting columns are unchanged; only the file format read/written differs
    - _Correctness_Properties: 4, 17_
    - _Requirements: 2.20, 3.3_

  - [ ] 5.5 Gate exports/merges to completed outputs only (Concern H I/O safety)
    - `app/server.py`: `geni_export` includes only items whose `status != "running"` (copy `_contacts` under `_geni_lock`); `api_export_all` selects only items with `status in {"done","stopped"}` AND an existing output, excluding running items' partial files; Chartporter export reads a status-gated/copied CSV so it never reads a file mid-write
    - **Preservation check**: completed-output exports still include the same items/columns/filters as today
    - _Bug_Condition: isBugCondition_race (op IN {export, export_all, merge} AND reads_incomplete_or_running_output)_
    - _Expected_Behavior: exports read only fully-written, status-gated outputs_
    - _Correctness_Properties: 15_
    - _Requirements: 2.15_

  - [ ] 5.6 Verify CSV exports + safe I/O (re-run Concern C/H exploration + PBT)
    - **Property 1: Expected Behavior** - every export is `text/csv` + `.csv`, completed-only
    - Re-run the C-export-format and H-race export_all cases from Task 1; add the PBT: random export datasets → CSV row/column sets equal the filtered source for every variant; add the interleaved reader/writer PBT → no torn reads / no partial merge
    - **Property 2: Preservation** - export columns/filters parity
    - Re-run the Task 2 export columns/filters baseline → CSV column set and per-filter row sets equal the recorded `.xlsx` oracle (only container format differs)
    - **EXPECTED OUTCOME**: format/empty-data cases pass; preservation parity holds
    - _Correctness_Properties: 4, 6, 15_
    - _Requirements: 2.20, 2.15, 3.3_

---

## Client + remaining fixes (depend on the foundations above)

- [ ] 6. Client timer restore + cross-tool timer (Concern A client)
  - Depends on Task 3 (`started_at` in snapshot) and Task 4.2 (`started_at` in cross-status)

  - [ ] 6.1 Restore the queue-bar timer from server truth
    - `app/static/app.js` & `app/static/genitractor.js`: replace `_timerStart` semantics — on `snapshot`/`item_started`, if any item is `running`, set `_timerStart = started_at*1000`, start the interval, and render `elapsed = now - started_at`; keep `stopTimer()`/`checkAllDone()` for the idle transition
    - _Bug_Condition: isBugCondition_timer (run_active AND navigated_or_refreshed, element "#timer")_
    - _Expected_Behavior: `#timer` resumes from `now - started_at` after navigation/refresh_
    - _Correctness_Properties: 1_
    - _Requirements: 2.1_

  - [ ] 6.2 Drive the cross-tool timer `#ctb-timer`
    - `app/static/app.js` & `app/static/genitractor.js` `initCrossToolBar()`: when the other tool is running and `started_at` is present, write `#ctb-timer` each poll and tick locally between polls
    - _Bug_Condition: isBugCondition_timer (element "#ctb-timer", never updated)_
    - _Correctness_Properties: 1_
    - _Requirements: 2.2_

  - [ ] 6.3 Verify timer behavior (re-run Concern A exploration + Property 2)
    - **Property 1: Expected Behavior** - timer survives navigation/refresh; `#ctb-timer` ticks
    - Re-run the A-timer cases from Task 1 (snapshot-with-running, refresh mid-run, cross-tool view, 8-minutes-ago tab) → all now pass
    - **Property 2: Preservation** - single-session timer
    - Re-run the Task 2 single-session timer baseline → still increments identically with no navigation/refresh
    - **Manual repro**: start a Chartporter run, switch to Genitractor and back → `#timer` resumes; open the other tool → `#ctb-timer` ticks
    - _Correctness_Properties: 1, 2_
    - _Requirements: 2.1, 2.2, 3.1_

- [ ] 7. Client stats restored from server snapshot (Concern E client)
  - Depends on Task 4 (`found` counter + running-only cross-status)

  - [ ] 7.1 Restore Chartporter stats on snapshot
    - `app/static/app.js` `snapshot` branch: restore `_totalArtists` and per-feed `counts` (`keep/review/drop`) from each item's `processed/keep/review/drop/total`, then call `updateStats()`
    - **Preservation check**: live single-session delta math is left intact (Property 11) — only the reconnect/snapshot path changes
    - _Bug_Condition: isBugCondition_stats (reconnected_midrun AND %CLEAN/%TOTAL counts_not_restored)_
    - _Expected_Behavior: `% CLEAN`/`% TOTAL` sourced from restored server-truth counts_
    - _Correctness_Properties: 9_
    - _Requirements: 2.8, 2.10_

  - [ ] 7.2 Restore Genitractor stats on snapshot
    - `app/static/genitractor.js` `snapshot` branch: restore `totalArtists/totalProcessed/totalFound` from the items' `total/processed/found`, then call `updateStats()`
    - _Bug_Condition: isBugCondition_stats (reconnected_midrun AND %FOUND/%TOTAL counts_not_restored)_
    - _Correctness_Properties: 9_
    - _Requirements: 2.9, 2.10_

  - [ ] 7.3 Verify stats accuracy (re-run Concern E exploration + PBT + Property 2)
    - **Property 1: Expected Behavior** - reconnect restores accurate `%`
    - Re-run the E-stats reconnect case from Task 1; add the PBT: random `processed/keep/review/drop/total` snapshots → restored client stats equal server truth (and never `NaN`)
    - **Property 2: Preservation** - single-session stats
    - Re-run the Task 2 single-session stats baseline → `% TOTAL`/`% CLEAN`/`% FOUND` and the click-to-toggle fraction view match the original
    - **Manual repro**: 1000-artist run ~60% done → refresh → `% TOTAL` ≈ 60% (not 0% then drift)
    - _Correctness_Properties: 9, 11_
    - _Requirements: 2.8, 2.9, 2.10, 3.5_

- [ ] 8. Client zero-total NaN guard (Concern G)
  - Independent of foundations; touches the same handlers as Task 7 (different code paths)

  - [ ] 8.1 Add and apply a safe `pct()` helper
    - `app/static/app.js` (`artist_done`) & `app/static/genitractor.js` (`contact_done`): add `pct(p,t){ return t>0 ? Math.floor(100*p/t) : 0 }` and use it everywhere a `%` is derived from `ev.total` (replacing the unguarded `Math.floor(100*ev.processed/ev.total)`)
    - _Bug_Condition: isBugCondition_nan (total == 0)_
    - _Expected_Behavior: render `0%` instead of `NaN%`_
    - _Correctness_Properties: 14_
    - _Requirements: 2.19_

  - [ ] 8.2 Verify NaN guard (re-run Concern G exploration + PBT)
    - **Property 1: Expected Behavior** - zero-total renders `0%`
    - Re-run the G-nan case from Task 1 (`total:0` events); add a unit test for `pct(p,0)===0` and a PBT over random `processed/total` → never `NaN`
    - **EXPECTED OUTCOME**: `0%` rendered; no `NaN%` anywhere
    - _Correctness_Properties: 14_
    - _Requirements: 2.19_

- [ ] 9. Export UI + empty-state in-UI messaging (Concern C UI)
  - Depends on Task 5 (CSV backend + status-gated routes)

  - [ ] 9.1 Chartporter persistent empty-state message
    - `app/static/app.js` `dl()`: keep parsing the JSON `{"error": ...}` contract but additionally render a **persistent** banner/inline message (not just the transient scrolling `sys()` line) when no completed output exists
    - _Bug_Condition: isBugCondition_export (NOT has_completed_output AND failure_surface == "transient_console")_
    - _Correctness_Properties: 5_
    - _Requirements: 2.5_

  - [ ] 9.2 Genitractor fetch+blob download with in-UI empty-state
    - `app/static/genitractor.js` export handler: replace `window.location.href="/api/genitractor/export"` with a `fetch()` — on `ok` trigger a blob download; on error show a persistent in-UI message; the page never navigates to a raw JSON body
    - **Preservation check**: the JSON error contract + status codes on the wire are unchanged (only client presentation changes) — Genitractor normal contacts export still downloads correctly
    - _Bug_Condition: isBugCondition_export (failure_surface == "raw_json_page")_
    - _Correctness_Properties: 5_
    - _Requirements: 2.6_

  - [ ] 9.3 Verify empty-state UX (re-run Concern C empty-state exploration + integration)
    - **Property 1: Expected Behavior** - persistent in-UI message, no silent no-op, no JSON navigation
    - Re-run the C-empty-state cases from Task 1; add the integration check: export per variant downloads a `.csv` opening with correct header + rows; empty-state shows a persistent message with no page navigation
    - _Correctness_Properties: 5_
    - _Requirements: 2.5, 2.6_

- [ ] 10. Clear controls on both queues (Concern B)
  - Depends on Task 3.3 (`_geni_lock` discipline) for the new Genitractor endpoint

  - [ ] 10.1 Add the Genitractor clear endpoint
    - `app/server.py`: new route `POST /api/genitractor/clear` that, under `_geni_lock`, removes non-running items and clears their `_contacts` (mirroring `clear_done`), then `_geni_broadcast` a fresh snapshot
    - _Bug_Condition: isBugCondition_clear (tool == "genitractor" AND clear_endpoint_absent)_
    - _Correctness_Properties: 3_
    - _Requirements: 2.4_

  - [ ] 10.2 Add and wire the CLEAR buttons
    - `app/static/index.html`: add a `CLEAR` button to the queue-bar (after `EXPORT`, before `.pill-divider`, matching `.queue-row`); `app/static/app.js`: wire to `POST /api/queue/clear`, guard with the existing `showConfirm(...)`, and on success reset `feeds`, `qState`, `_totalArtists`, per-feed counts, then `updateStats()`
    - `app/static/genitractor.html`: add a matching `CLEAR` button; `app/static/genitractor.js`: wire to `POST /api/genitractor/clear` and reset `totalProcessed/totalArtists/totalFound`, `qState`, and `#feeds-grid`
    - **Preservation check**: the existing `/api/queue/clear` → `clear_done()` behavior and STOP/EXPORT controls are unchanged; running items are NOT cleared
    - _Bug_Condition: isBugCondition_clear (clear_button_absent)_
    - _Correctness_Properties: 3_
    - _Requirements: 2.3, 2.4_

  - [ ] 10.3 Verify clear controls (re-run Concern B exploration + unit test)
    - **Property 1: Expected Behavior** - both queues clear and client state resets
    - Re-run the B-clear cases from Task 1 (Clear control now present; `POST /api/genitractor/clear` → 200); add the unit test: the new endpoint clears items/`_contacts` under the lock and broadcasts a snapshot
    - **Manual repro**: fill each queue with `done`/`error` items → Clear resets queue/feed/stats
    - _Correctness_Properties: 3_
    - _Requirements: 2.3, 2.4_

- [ ] 11. Genius pacing — backoff, pause, reconciled interval, cross-pass mutex (Concern D)
  - Sequenced after Task 5.4 so the `_genius_worker` CSV changes land before this touches the same worker

  - [ ] 11.1 Reconcile interval + escalating backoff in the Genius source
    - `app/sources/genius.py`: standardize `_MIN_INTERVAL = 0.5` (2 req/s) and fix the stale "0.25s" comment in `_geni_worker`; replace the single-retry 429 block with an escalating backoff helper (delays `2,4,8,16,32`s, capped, with jitter) that also triggers on Cloudflare `1015` and `403`-HTML bodies (detect via status + `Content-Type`/body sniff); on exhaustion surface a typed "rate-limited" outcome instead of silently returning `None`
    - _Bug_Condition: isBugCondition_genius (response IN {429,1015,403_html} AND NOT escalating_backoff_applied; interval_inconsistent)_
    - _Correctness_Properties: 7_
    - _Requirements: 2.7_

  - [ ] 11.2 Periodic pause during large Genitractor runs
    - `app/server.py` `_geni_worker`: add configurable `GENI_PAUSE_EVERY = 250` and `GENI_PAUSE_SECONDS = 5`; sleep `GENI_PAUSE_SECONDS` every `GENI_PAUSE_EVERY` artists
    - _Bug_Condition: isBugCondition_genius (n_artists large AND NOT periodic_pause_applied)_
    - _Correctness_Properties: 7_
    - _Requirements: 2.7_

  - [ ] 11.3 Cross-pass mutual exclusion
    - `app/server.py`: add a module-level `genius_pass_lock = threading.Lock()` shared by `_genius_worker` and `_geni_worker`; acquire it for the duration of each pass so the two never call Genius concurrently (distinct from `genius._genius_lock`, which only paces individual request timing)
    - **Preservation check**: `genius._genius_lock` per-request pacing is unchanged; a normal-sized run with a single active pass behaves as today
    - _Bug_Condition: isBugCondition_genius (other_pass_active AND NOT passes_mutually_excluded)_
    - _Correctness_Properties: 8_
    - _Requirements: 2.16_

  - [ ] 11.4 Verify Genius pacing (re-run Concern D exploration + unit + integration)
    - **Property 1: Expected Behavior** - backoff escalates, pause fires, passes serialized
    - Re-run the D-genius case from Task 1; add unit tests for the backoff delay schedule (429/1015/403-HTML) and interval reconciliation; add the integration check: Genitractor run + Genius social pass started together → serialized via `genius_pass_lock`
    - **EXPECTED OUTCOME**: a simulated 4000-artist run with repeated 429/1015 backs off, pauses, and completes
    - _Correctness_Properties: 7, 8_
    - _Requirements: 2.7, 2.16_

- [ ] 12. Init resilience + collapsible rewrite + menu guard + CSS (Concern F)
  - Independent UI hardening; safe to land late

  - [ ] 12.1 Make `DOMContentLoaded` init resilient
    - `app/static/app.js` & `app/static/genitractor.js`: wrap each `init*()` call in its own `try/catch` (log to `sys(...,"bad")` on failure) so one failure cannot unwire later handlers (including the tools dropdown)
    - _Bug_Condition: isBugCondition_ui (an_earlier_init_threw AND later_handlers_unwired)_
    - _Correctness_Properties: 12_
    - _Requirements: 2.11_

  - [ ] 12.2 Rewrite the collapsible mechanism
    - `app/static/app.js` & `app/static/genitractor.js` `initCollapsible()`: drive open/close entirely by a single class via `grid-template-rows: 1fr → 0fr` (or a measured max-height that does not rely on `scrollHeight` being non-zero); remove the inline-`maxHeight` + `!important` conflict and the `350ms` `setTimeout`
    - `app/static/styles.css` & `app/static/genitractor.css`: drop the `max-height:0 !important` rule in favor of the class-driven transition
    - _Bug_Condition: isBugCondition_ui (toggle_collapsible AND NOT content_present AND relies_on_zero_scrollHeight; rapid_toggle AND overlapping_timers)_
    - _Correctness_Properties: 12_
    - _Requirements: 2.12, 2.13_

  - [ ] 12.3 Add the Genitractor menu `stopPropagation` guard
    - `app/static/genitractor.js` `initToolsDropdown()`: add `menu.addEventListener("click", e=>e.stopPropagation())` (matching `app.js`) so a click inside the menu does not bubble to the document handler that closes it
    - _Bug_Condition: isBugCondition_ui (page == "genitractor" AND open_menu AND missing_stopPropagation_guard)_
    - _Correctness_Properties: 12_
    - _Requirements: 2.11_

  - [ ] 12.4 Verify UI behavior (re-run Concern F exploration + Property 2)
    - **Property 1: Expected Behavior** - resilient init, robust collapsible, menu guard
    - Re-run the F-ui cases from Task 1 (early init throw → dropdown still wired; empty-content toggle; rapid toggle; Genitractor menu click)
    - **Property 2: Preservation** - UI in a normal session
    - Re-run the Task 2 modals/UI normal-session baseline → dropdown and collapsibles navigate/show-hide exactly as today; unaffected modals untouched
    - _Correctness_Properties: 12, 13_
    - _Requirements: 2.11, 2.12, 2.13, 3.9_

- [ ] 13. Bounded feed-log DOM on both pages (Concern I)
  - Independent; safe to land late

  - [ ] 13.1 Cap rendered feed blocks
    - `app/static/app.js` `addArtistToFeed`: after append, trim `feed.log` via `while(feed.log.children.length>FEED_BLOCK_CAP) feed.log.firstChild.remove()` (`FEED_BLOCK_CAP = 200`, mirroring the console cap)
    - `app/static/genitractor.js` `addContactToFeed`: apply the same trim on `#feeds-grid`
    - **Preservation check**: under-cap runs render exactly as today; SSE event semantics unchanged
    - _Bug_Condition: isBugCondition_dom (rendered_blocks > FEED_BLOCK_CAP AND NOT trimmed)_
    - _Correctness_Properties: 16_
    - _Requirements: 2.17_

  - [ ] 13.2 Verify DOM cap (re-run Concern I exploration + PBT)
    - **Property 1: Expected Behavior** - feed DOM stays bounded
    - Re-run the I-dom case from Task 1; add the PBT: large block streams → DOM node count stays ≤ cap on both pages
    - _Correctness_Properties: 16_
    - _Requirements: 2.17_

---

- [ ] 14. Checkpoint — full platform regression & preservation verification
  - Run the platform (`run.py` → `app/server.py`) on `feat/catalog-audit-v5` and confirm every fix-check and every preservation requirement
  - **Fix-checks (re-run the full Task 1 suite — all areas A–I now pass):**
    - timer survives navigation/refresh and `#ctb-timer` ticks; both queues clear; every export is `text/csv`+`.csv`; empty-state shows persistent in-UI message; Genius backs off/pauses/serializes; stats restore from snapshot; cross-status counts running-only; resilient init/collapsible/menu; `0%` not `NaN%`; torn-read-free state + completed-only exports; feed DOM bounded
  - **Preservation (re-run the full Task 2 baseline — must still pass):**
    - **Audit equivalence**: identical KEEP/REVIEW/DROP_* classification and Status Reason / labels (Property 17, 3.2)
    - **Export column/filter parity**: CSV column set and per-filter row sets equal the recorded `.xlsx` oracle for keep/review/drops/all, merge-all, and Genitractor contacts (Property 6, 3.3)
    - **Single-session timer/stats**: timer and `% TOTAL`/`% CLEAN`/`% FOUND` (with click-to-toggle fraction view) match original with no navigation/refresh (Properties 2, 11; 3.1, 3.5)
    - **Concurrency model**: Chartporter still runs up to 4 concurrent items / 4 parallel artists / 25-row checkpoints; Genitractor normal-run extraction/display/export unchanged (3.6, 3.7)
    - **Unaffected modals/SSE**: API-key/feedback/STOP/upload/pills/global-filters and SSE event types/reconnect behavior unchanged (Properties 13, 17; 3.4, 3.8, 3.9)
  - Ensure all unit, property-based, and integration tests pass; ask the user if any question or ambiguity arises
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

---

## Task Dependency Graph

```
1. Bug-condition exploration (Property 1)        [FAILS on unfixed code]
2. Preservation baseline (Property 2)            [PASSES on unfixed code]
        │  (both precede all implementation)
        ▼
────────────────── Backend foundations ──────────────────
3. Server started_at + _geni_lock discipline (A backend, H locking)
        ├─────────────► 4. Server-truth counts + cross-status running-only (E backend, 1.18)
        │                       │
        ├─────────────► 5. CSV export rewrite + safe I/O (C backend, H export safety)
        │                       │
        └───────────────► 10. Clear controls (B)        [needs 3.3 lock for geni clear endpoint]
                                │
──────────────────── Client + remaining ─────────────────
3,4 ──► 6. Client timer restore + #ctb-timer (A client)
4   ──► 7. Client stats restore from snapshot (E client)
        8. NaN pct() guard (G)                   [independent; pairs with 7's handlers]
5   ──► 9. Export UI + empty-state messaging (C UI)
5.4 ──► 11. Genius pacing: backoff/pause/mutex (D)   [after _genius_worker CSV change]
        12. Init resilience + collapsible + menu guard + CSS (F)   [independent UI]
        13. Feed DOM cap (I)                     [independent UI]
        │
        ▼
14. Checkpoint — full regression & preservation verification
        depends on: 3,4,5,6,7,8,9,10,11,12,13
```

**Critical path:** 1 → 2 → 3 → {4, 5} → {6, 7, 9, 10, 11} → 14

**Ordering rationale (minimize breakage):**
- **Foundations first** — `started_at`, the `found` counter / running-only `cross-status`, and the
  `_geni_lock` discipline (Tasks 3–4) are server-side contracts the client timer (6) and client stats
  (7) restore from; they must exist before the client reads them.
- **CSV writer before UI** — the CSV module, checkpoint format, routes, and `_genius_worker` read/append
  (Task 5) land before the export UI/empty-state wiring (Task 9) so the client always has a `text/csv`
  contract to call.
- **Independent UI fixes last** — NaN guard (8), Genius pacing (11), init/collapsible (12), and DOM cap
  (13) touch isolated code paths and carry the lowest regression risk, so they sequence after the
  shared contracts settle.
