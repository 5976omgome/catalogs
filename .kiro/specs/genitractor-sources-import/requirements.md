# Requirements Document

## Introduction

This feature modifies the existing **catalogs** platform (branch `feat/catalog-audit-v5`), which ships two tools served by one Flask app (`app/server.py`):

- **Chartporter** — the catalog audit tool (`app/static/index.html` + `app/static/app.js`), backed by `app/jobs.py` (`JobManager`), `app/audit.py`, `app/excel.py`, and `app/csv_export.py`. It classifies artists as KEEP / REVIEW / DROP.
- **Genitractor** — the contact-extraction tool (`app/static/genitractor.html` + `app/static/genitractor.js`), backed by the `/api/genitractor/*` routes in `app/server.py` and `app/sources/genius.py`. It pulls social handles per artist from the Genius API.

The feature has four goals:

1. Narrow Genitractor's data sources to **Instagram and Facebook only** — **remove Twitter, Website, and YouTube entirely** (no extraction, no feed rows, no CSV columns, no website-derivation fallback, no bio/description parsing) — so the feed and exported CSV columns become **Artist Name, Instagram, Facebook, Match Confidence**.
2. **Maximize Instagram/Facebook capture** by replacing the old blind first-hit / 3-character-prefix artist match with a **balanced artist-matching strategy** that examines several search hits and records a per-artist **Match Confidence** (Exact or Uncertain) to control false matches.
3. **Remove the social columns (Instagram, YouTube, Facebook, Twitter) from Chartporter's output and export** — socials belong to Genitractor only.
4. Add an **Import** control to the Genitractor queue bar offering "Import from disk" and "Import from Chartporter".

**Social data source.** Both Genitractor socials (Instagram and Facebook) are sourced from the **Genius API**: `GET /search` resolves the artist id, then `GET /artists/:id` returns the artist object, accessed via `app/sources/genius.py` `get_socials`. The Genius artist object exposes `instagram_name` and `facebook_name` directly, which are the only two fields this feature reads. The object also exposes `twitter_name`, but Twitter is intentionally dropped. Website and YouTube are **not** extracted at all: the Genius API exposes no dedicated website or youtube field, and this feature deliberately does not parse them from the artist `description`/`description_annotation` and does not derive a website from the Instagram handle.

**Extraction stays fast.** Because Genitractor no longer issues any per-artist website HEAD request and no longer parses bio/description text, extraction does only the two Genius API calls per artist (search + artist lookup). This keeps extraction fast, consistent with prior "too slow" feedback.

All existing Chartporter audit/classification behavior, the plain-CSV export format, the bug fixes already on this branch, and the SSE/queue semantics must be preserved.

## Glossary

- **Chartporter**: The catalog audit tool. Frontend `app/static/index.html` + `app/static/app.js`; backend `app/jobs.py` (`JobManager`) + `app/audit.py`. Produces KEEP/REVIEW/DROP classifications.
- **Genitractor**: The contact-extraction tool. Frontend `app/static/genitractor.html` + `app/static/genitractor.js`; backend `/api/genitractor/*` routes in `app/server.py`.
- **Genius_Source**: The module `app/sources/genius.py`, specifically `get_socials(artist)`, which queries the Genius API — `GET /search` to resolve the artist id, then `GET /artists/:id` for the artist object — and returns a dict of social handles or the `RATE_LIMITED` sentinel. This feature reads only `instagram_name` and `facebook_name` from the artist object; `twitter_name` is dropped, and no website or youtube value is read or parsed.
- **Genitractor_Extractor**: The Genitractor worker `_geni_worker(item)` in `app/server.py` that iterates artists in an uploaded CSV and calls `Genius_Source`.
- **Genitractor_Exporter**: The route `geni_export()` (`/api/genitractor/export`) in `app/server.py` that writes the contacts CSV.
- **Genitractor_Feed**: The live feed rendering in `app/static/genitractor.js` (`addContactToFeed`) plus its SSE handling.
- **Chartporter_Exporter**: The CSV writer path used by Chartporter (`app/csv_export.py` `write_csv` / `filter_csv_by_status` / `merge_all_csv`), driven by the audit column set `AUDIT_COLUMNS` in `app/excel.py`.
- **Contact_Record**: One artist's extracted result. After this feature the dict in `_geni_worker` has keys `artist`, `instagram`, `facebook`, and `match_confidence` (no `youtube`, no `twitter`, no `website`).
- **Social_Field**: One of the contact channels surfaced by Genitractor: Instagram or Facebook (after this feature).
- **Match_Confidence**: A per-artist value of `Exact` or `Uncertain` recorded by the Genitractor_Extractor describing how confidently the resolved Genius artist matches the queried artist name. Surfaced as a feed marker and a CSV column.
- **No_Profile_Outcome**: The result when no acceptable Genius artist match is found among the examined search hits — an inherent data-source/matching limit, not a code failure.
- **Rate_Limited_Outcome**: The `RATE_LIMITED` sentinel returned by `Genius_Source` when Genius rate-limits the platform past the backoff schedule (`_BACKOFF_SCHEDULE` in `app/sources/genius.py`).
- **Extraction_Error_Outcome**: The result when extraction raises a network error or exception for an artist; mutually exclusive from No_Profile_Outcome and Rate_Limited_Outcome, and the only outcome that places an artist in the errored state.
- **Found_Outcome**: The result when an artist's Contact_Record has at least one non-empty Social_Field (Instagram or Facebook); the only outcome that increments the Found_Count.
- **Found_Count**: The per-item `found` counter in `_geni_worker` — incremented when a `Contact_Record` has at least one non-empty `Social_Field`.
- **Import_Modal**: The new popup opened from the Genitractor queue bar offering "Import from disk" and "Import from Chartporter".
- **Import_Service**: The new backend behavior that copies/enqueues Chartporter's currently-queued files into the Genitractor queue.
- **Queue_Manager**: The Chartporter `JobManager` instance in `app/server.py` (`_manager`), whose queued items are exposed via `snapshot()`.
- **SSE_Stream**: The server-sent-events channels (`/api/stream` for Chartporter, `/api/genitractor/stream` for Genitractor) and their `snapshot` / `item_added` / `item_started` / `contact_done` / `item_done` event contract.
- **KEEP/REVIEW/DROP**: The audit classification values written to the `Status` column by `app/audit.py`, consumed by export filters in `app/csv_export.py` and `app/excel.py`.

## Requirements

### Requirement 1: Limit Genitractor sources to Instagram and Facebook

**User Story:** As a label scout, I want Genitractor to collect and show only Instagram and Facebook, so that the contact set reflects the two channels we actually use for outreach and extraction stays fast.

_Relevant files: `app/server.py` (`_geni_worker`, `geni_export`), `app/static/genitractor.js` (`addContactToFeed`), `app/sources/genius.py` (`get_socials`), `app/sources/email_scraper.py` (`find_artist_website`)._

#### Acceptance Criteria

1. THE Genitractor_Extractor SHALL build each Contact_Record containing only Instagram, Facebook, and Match_Confidence fields, with no key or field named or representing Twitter (`twitter`, `twitter_name`, or `X`), Website (`website`), or YouTube (`youtube`).
2. WHERE Genius_Source returns a `twitter_name` value, THE Genitractor_Extractor SHALL drop that value while retaining the Instagram and Facebook values when assembling the Contact_Record.
3. THE Genitractor_Extractor SHALL NOT parse the Genius artist `description`/`description_annotation` for any website or YouTube link, and SHALL NOT read any website or youtube value from the Genius artist object.
4. THE Genitractor_Extractor SHALL NOT issue any per-artist website HTTP request and SHALL NOT call the `find_artist_website` Instagram-handle-to-`.com` derivation for this feature.
5. WHEN the Genitractor_Feed renders an artist block, THE Genitractor_Feed SHALL enumerate only the Instagram and Facebook rows and SHALL NOT render a Twitter ("X"), Website, or YouTube row.
6. THE Genitractor_Exporter SHALL produce a CSV whose header row and every data row contain no Twitter, Website, or YouTube cell.

### Requirement 2: Genitractor feed and export column set

**User Story:** As a label scout, I want the Genitractor feed and CSV to show exactly Artist Name, Instagram, Facebook, and Match Confidence, so that the export matches our outreach workflow and flags risky matches.

_Relevant files: `app/server.py` (`geni_export` header row), `app/static/genitractor.js` (`addContactToFeed` rows)._

#### Acceptance Criteria

1. THE Genitractor_Exporter SHALL write exactly 4 columns in the fixed order `Artist Name`, `Instagram`, `Facebook`, `Match Confidence`, with no added, omitted, or reordered columns.
2. WHEN the Genitractor_Exporter writes a data row, THE Genitractor_Exporter SHALL write the artist name, the Instagram value, the Facebook value, and the Match_Confidence value aligned to their column positions, keeping every row at 4 fields.
3. WHEN a field value contains a comma, double-quote, carriage return, or line feed, THE Genitractor_Exporter SHALL quote that field and double any embedded double-quote, consistent with the Python `csv` module default behavior, with no workbook styling.
4. WHERE a Social_Field value is empty, THE Genitractor_Exporter SHALL write a zero-length field that keeps the row at 4 aligned fields, and THE Genitractor_Feed SHALL render an em-dash ("—") placeholder for that row tied to the same empty condition.
5. THE Genitractor_Feed SHALL display the Social_Field rows in the order Instagram, Facebook.
6. THE Genitractor_Exporter and Genitractor_Feed SHALL treat a Social_Field value as empty WHEN it is null, missing, or zero-length after trimming.

### Requirement 3: Surface and normalize Instagram and Facebook

**User Story:** As a maintainer, I want every Instagram and Facebook handle Genius returns to be surfaced and normalized, so that fixable yield loss from dropped or mis-parsed fields is eliminated.

_Relevant files: `app/sources/genius.py` (`get_socials`, `_normalize`), `app/server.py` (`_geni_worker` handle-to-URL conversion)._

#### Acceptance Criteria

1. WHEN Genius_Source obtains an `instagram_name` that is a full URL beginning with `http` or `https` (detected case-insensitively), THE Genitractor_Extractor SHALL emit that Instagram value as-is; otherwise THE Genitractor_Extractor SHALL strip a leading `@`, surrounding Unicode whitespace, and leading and trailing slashes from the handle, then prefix exactly one `https://instagram.com/`, with double-prefix protection so no value receives two scheme or domain prefixes.
2. WHEN Genius_Source obtains a `facebook_name`, THE Genitractor_Extractor SHALL emit it as-is WHEN it begins with `http`; otherwise THE Genitractor_Extractor SHALL strip surrounding Unicode whitespace and leading and trailing slashes, then prefix exactly one `https://facebook.com/`, with double-prefix protection so no value receives two scheme or domain prefixes.
3. THE Genitractor_Extractor SHALL trim surrounding Unicode whitespace from the Instagram and Facebook values before storing them in the Contact_Record.
4. IF Genius_Source returns an Instagram or Facebook value that is present but empty or whitespace-only, THEN THE Genitractor_Extractor SHALL treat that Social_Field as not found and store a zero-length value.

### Requirement 4: Maximize capture with balanced artist matching and a confidence flag

**User Story:** As a label scout, I want Genitractor to find Instagram/Facebook for as many artists as possible while flagging risky matches, so that I maximize coverage without trusting wrong guesses.

_Relevant files: `app/sources/genius.py` (`get_socials` artist-match logic, `_normalize`), `app/server.py` (`_geni_worker` `contact_done` event, `found` counter)._

#### Acceptance Criteria

1. WHEN resolving an artist from `GET /search`, THE Genius_Source SHALL examine up to the first 10 search hits in Genius result order rather than only the first hit.
2. THE Genius_Source SHALL compute a normalized form of an artist name by case-folding, trimming, collapsing internal whitespace, removing diacritics/accents, stripping punctuation, removing a leading "the", and removing common join tokens (`feat.`, `featuring`, `&`, `x`, `and`).
3. THE Genius_Source SHALL classify a hit as an exact match WHEN the hit's normalized artist name equals the normalized query name.
4. WHEN an exact match exists among the examined hits, THE Genius_Source SHALL select that hit and set Match_Confidence to `Exact`.
5. WHEN no exact match exists but a close match exists — one normalized name is a prefix or substring of the other, or the two differ only by removable tokens — THE Genius_Source SHALL select the best such hit and set Match_Confidence to `Uncertain`.
6. THE Genius_Source SHALL NOT accept a hit that is neither an exact nor a close normalized match, replacing and removing the prior blind first-hit / 3-character-prefix fallback.
7. WHERE multiple equally-good matches exist, THE Genius_Source SHALL prefer the most popular/relevant hit as ordered by Genius.
8. THE Genitractor_Extractor SHALL record a Match_Confidence value of `Exact` or `Uncertain` for each artist with an accepted match, and SHALL flag `Uncertain` matches in both the live feed (a visible marker on the artist block) and the exported CSV (the `Match Confidence` column value).
9. WHEN no acceptable match is found among the examined hits, THE Genitractor_Extractor SHALL classify the artist as a No_Profile_Outcome, which is distinct from Rate_Limited_Outcome and Extraction_Error_Outcome and SHALL NOT be treated as a failure or place the artist in the errored state.
10. WHEN Genius_Source returns the `RATE_LIMITED` sentinel, THE Genitractor_Extractor SHALL mark that artist's result as a Rate_Limited_Outcome and SHALL NOT classify the artist as a No_Profile_Outcome.
11. WHEN Genius_Source raises a network error or exception during extraction, THE Genitractor_Extractor SHALL classify the artist as an Extraction_Error_Outcome, mutually exclusive from No_Profile_Outcome and Rate_Limited_Outcome.
12. THE Genitractor_Extractor SHALL set the `contact_done` SSE payload to indicate exactly one outcome per event (Found_Outcome, No_Profile_Outcome, Rate_Limited_Outcome, or Extraction_Error_Outcome) and SHALL increment the processed counter by exactly 1 for every outcome.

### Requirement 5: Coverage and found counting

**User Story:** As a label scout, I want a found result whenever an artist yields Instagram or Facebook, so that coverage metrics reflect the channels we keep and the new matching never reduces yield.

_Relevant files: `app/server.py` (`_geni_worker` `found` counter, `has_social`), `app/static/genitractor.js` (`updateStats`, badge logic)._

#### Acceptance Criteria

1. THE Genitractor_Extractor SHALL treat a Social_Field as non-empty WHEN it has at least 1 non-whitespace character after trimming.
2. WHEN an artist's Contact_Record has at least one non-empty Social_Field among Instagram or Facebook, THE Genitractor_Extractor SHALL classify the artist as a Found_Outcome and increment the Found_Count at most once for that artist, regardless of whether one or both fields are non-empty; no other outcome SHALL increment the Found_Count.
3. THE Genitractor_Feed found/empty badge SHALL be computed from Instagram and Facebook only.
4. WHEN at least one of Instagram or Facebook holds a present value, THE Genitractor_Feed SHALL set the badge to the found state, and WHEN both Social_Field values are absent, THE Genitractor_Feed SHALL set the badge to the empty state.
5. THE Genitractor_Extractor SHALL produce a Found_Count greater than or equal to the Found_Count produced by the prior exact-only (blind first-hit) matching for every input (monotonicity).

### Requirement 6: Remove social columns from Chartporter

**User Story:** As a catalog auditor, I want Chartporter's output to contain no social columns, so that the audit export stays focused on classification and socials live only in Genitractor.

_Relevant files: `app/excel.py` (`AUDIT_COLUMNS` includes `Instagram`, `YouTube`, `Facebook`; `_WIDTHS`), `app/jobs.py` (`_audit_one`/socials write block, `_write_partial`), `app/static/app.js` (`addArtistToFeed` GENIUS row, `gf-socials` toggle), `app/static/index.html` (`gf-socials`)._

#### Acceptance Criteria

1. THE Chartporter_Exporter SHALL produce output containing no header named `Instagram`, `YouTube`, `Facebook`, or `Twitter` across every output path: the full export, the status-filtered export, the merged combined export, and the 25-row partial/checkpoint output via `_write_partial`.
2. THE Chartporter `AUDIT_COLUMNS` set SHALL define exactly `Status`, `Status Reason`, `iTunes Labels`, `Deezer Labels`, `Earliest Year`, and `AI Note`.
3. THE Chartporter feed SHALL render no GENIUS social-links row.
4. THE Chartporter global filter bar SHALL present no `gf-socials` toggle.
5. THE Chartporter `_WIDTHS` mapping SHALL contain no `Instagram`, `YouTube`, or `Facebook` width entry.

### Requirement 7: Preserve Chartporter audit and classification logic

**User Story:** As a catalog auditor, I want the KEEP/REVIEW/DROP logic untouched by the social-column removal, so that audit results stay identical.

_Relevant files: `app/audit.py` (`audit_artist`, Status assignment), `app/csv_export.py` (`filter_csv_by_status`), `app/excel.py` (`filter_xlsx_by_status`)._

#### Acceptance Criteria

1. THE Chartporter_Auditor SHALL assign a Status value from the set {`KEEP`, `DROP_MAJOR`, `DROP_LICENSED`, `DROP_THIRDPARTY`, `REVIEW`} byte-for-byte identical to the pre-removal values for a given input.
2. WHEN a Chartporter export filter is requested, THE Chartporter_Exporter SHALL select the same rows in the same count and order as before the social columns were removed.
3. WHEN the `ALL` filter is requested, THE Chartporter_Exporter SHALL select every row.
4. WHEN a `DROP` filter is requested, THE Chartporter_Exporter SHALL match rows by the `DROP`-prefix rule, selecting `DROP_MAJOR`, `DROP_LICENSED`, and `DROP_THIRDPARTY`.
5. THE Chartporter_Auditor SHALL write `iTunes Labels` and `Deezer Labels` values byte-for-byte identical to the pre-removal values.
6. THE Chartporter_Auditor SHALL write the `Status Reason` text and the `AI Note` byte-for-byte unchanged from the pre-removal values.
7. WHERE the `_geni_worker` path still runs, THE Chartporter_Exporter SHALL exclude its Instagram and Facebook output from the export columns.
8. THE Chartporter_Exporter SHALL produce plain CSV consisting of the header plus raw rows, with no styling, fills, fonts, column widths, frozen panes, or filters.

### Requirement 8: Genitractor Import control and modal

**User Story:** As a label scout, I want an Import button in the Genitractor queue bar that opens a popup with two choices, so that I can load artists from disk or from Chartporter without leaving Genitractor.

_Relevant files: `app/static/genitractor.html` (queue bar currently has ADD/RUN/STOP/EXPORT/CLEAR; existing modal markup pattern), `app/static/genitractor.js` (modal init pattern, `uploadFile`)._

#### Acceptance Criteria

1. THE Genitractor_UI SHALL display an Import control in the queue bar alongside the ADD, RUN, STOP, EXPORT, and CLEAR controls.
2. WHEN the Import control is activated, THE Genitractor_UI SHALL open the Import_Modal showing exactly two options, "Import from disk" and "Import from Chartporter".
3. WHEN the Import_Modal opens, THE Genitractor_UI SHALL move focus to the first option.
4. WHEN the "Import from disk" option is activated, THE Genitractor_UI SHALL open a file dialog restricted to `.csv` and `.tsv` files that allows selecting one or more files.
5. IF a selected file is not a `.csv` or `.tsv` file, THEN THE Genitractor_UI SHALL reject that file without posting it and SHALL provide an indication to the user.
6. WHEN a `.csv` or `.tsv` file is selected through "Import from disk", THE Genitractor_UI SHALL post each selected file to `/api/genitractor/upload` and THE Genitractor_Extractor SHALL enqueue each as a separate Genitractor queue item exactly as the existing ADD control does.
7. WHEN an option's action is triggered, THE Genitractor_UI SHALL close the Import_Modal.
8. WHEN Escape is pressed, or the close control is activated, or an outside-click occurs, THE Genitractor_UI SHALL close the Import_Modal without enqueuing anything.

### Requirement 9: Import from Chartporter

**User Story:** As a label scout, I want to pull the files currently queued in Chartporter straight into Genitractor, so that I can run contact extraction on the same catalog I am auditing.

_Relevant files: `app/server.py` (`Queue_Manager` `_manager`, `snapshot()`, `JobItem.path`, `UPLOAD_DIR`, `GENI_UPLOAD_DIR`, `geni_upload` enqueue pattern), `app/jobs.py` (`JobItem`)._

#### Acceptance Criteria

1. WHEN the "Import from Chartporter" option is activated, THE Import_Service SHALL read a point-in-time snapshot of the items in the Queue_Manager whose status is "queued" only, excluding running, done, stopped, and error items.
2. WHEN copying a Chartporter-queued file into Genitractor, THE Import_Service SHALL copy it into the Genitractor upload directory using the existing UUID-prefix collision scheme so that no existing file is overwritten, and SHALL preserve the display filename distinct from the unique on-disk name.
3. WHEN the Import_Service enqueues Genitractor items, THE SSE_Stream SHALL emit exactly one `item_added` event per imported item so the Genitractor queue updates live.
4. IF there are zero queued-status files in the Chartporter queue, THEN THE Import_Service SHALL enqueue no items and THE Genitractor_UI SHALL inform the user that there is nothing to import.
5. IF a queued item's source file is missing on disk, THEN THE Import_Service SHALL skip that item with an error indication and continue processing the remaining items.
6. THE Import_Service SHALL prevent duplicate imports by source path.
7. THE Import_Service SHALL NOT remove, alter, or reorder the items in the Chartporter queue.

### Requirement 10: Preserve existing branch fixes and SSE/queue semantics

**User Story:** As a maintainer, I want all earlier fixes on this branch and the SSE/queue behavior preserved, so that this feature does not regress prior work.

_Relevant files: `app/server.py` (`_geni_worker` periodic pause, `geni_clear`, `geni_stream` snapshot, `cross-status`), `app/sources/genius.py` (`RATE_LIMITED`, `_request_with_backoff`), `app/static/genitractor.js` (`startTimer`/`resumeTimer`, `clearAll`), `app/jobs.py` (`clear_done`, `start`)._

#### Acceptance Criteria

1. THE Genius_Source SHALL keep its escalating backoff schedule of exactly `[2, 4, 8, 16, 32]` seconds over up to 5 attempts, returning the `RATE_LIMITED` sentinel on exhaustion, with a minimum interval of 0.5 seconds (at most 2 requests per second), unchanged by this feature.
2. THE Genitractor_Extractor SHALL keep the periodic pause of 5 seconds every 250 artists (`GENI_PAUSE_EVERY` / `GENI_PAUSE_SECONDS`) unchanged.
3. WHEN a Genitractor clear is requested, THE Genitractor backend SHALL retain queued and running items and drop done, stopped, and error items, as the current `geni_clear` does.
4. WHEN a new SSE subscriber connects, THE SSE_Stream SHALL send exactly one `snapshot` event enumerating each item's id, filename, status, processed, total, and started_at.
5. THE Genitractor timer SHALL resume from the minimum `started_at` of running items after a reconnect and SHALL stop at 00:00 when no items are running.
6. THE cross-tool status endpoint SHALL report running-only progress sums for both Chartporter and Genitractor, with `started_at` set to the minimum `started_at` of running items.
7. WHEN total equals 0, THE Genitractor_UI SHALL report 0% progress and SHALL never display `NaN%`.
8. THE Genitractor_Feed and console SHALL cap their DOM nodes at 200 entries.
9. THE Genitractor_Exporter SHALL produce plain CSV output consisting of the header plus raw values, rendering `None` and `"nan"` as empty, with column and status-filter parity including the `ALL` rule and the `DROP`-prefix matching.
