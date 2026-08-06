# Implementation Notes — pelis-feed

## Scope implemented

All milestones M1–M10 and M12–M19 are implemented and running in production. M11 (Design Feed) is documented and awaiting implementation.

- **M1 — Ingestion:** CLI ingester, RSS fetch/parse, dedup, storage
- **M2 — Enrichment:** On-demand OMDb enrichment via web UI; stores `imdb_id` for direct linking
- **M3 — Web Application:** FastAPI + React CDN frontend; movie list with Filtered/All toggle; rating badges link to IMDb/RT
- **M4 — Alerting + Polish:** Feed health tracking per feed; SMTP alert on 24h downtime
- **M5 — News Feeds + Filter Processor:** News ingestion (all types); CLI Filter Processor (regex only); News tab in web UI; export/import for AI-filtered feeds
- **M6 — Series Feed:** EZTV ingestion; Series tab with read-tracking; feed health + alerting
- **M7 — Series Two-Table Split + Ignore:** Split `series` into `series` (title-level) + `series_episodes` (episode-level); `is_ignored` on `series` row; two-toggle view (Unread/Read × Not-Ignored/Ignored); Ignore toggle at series title level
- **M8 — Movies Two-Toggle View:** Replace Filtered/All toggle with two independent toggles — Read/Unread and Flagged/Un-Flagged
- **M9 — News Feed Simplification + Read/Unread Toggle:** Remove Import, raw sub-view, and Keep as Context; add Read/Unread toggle to all news feed types
- **M10 — Drop ai_filtered Feed Type:** Remove `ai_filtered` feed type entirely from config, backend routes, and frontend; `ai_filtered_views` table stays in DB as dead weight

## Files touched

### src/common/ (shared components)
- `src/common/models.py` — SQLAlchemy models: `Movie`, `Series`, `SeriesEpisode`, `FeedHealth`, `NewsItem`, `Filter`, `AIFilteredView` (legacy, table retained in DB)
- `src/common/db.py` — Database engine/session setup (MySQL + SQLite)
- `src/common/config.py` — YAML config loading and validation

### src/cli/ (ingester + filter processor)
- `src/cli/main.py` — Entry point: fetches movie feed then all configured news feeds; stores results; updates `FeedHealth`; sends SMTP alert on downtime
- `src/cli/filter.py` — Entry point: syncs `filters` table from config; regex-flags `news_items` for `filtered` feeds by setting `matched_filter_id`; no AI invocation; no row deletion
- `src/cli/fetcher.py` — RSS feed fetching and parsing; `fetch_feed` for movies; `fetch_news_feed` for news (normalises RSS 2.0 and Atom via feedparser)
- `src/cli/dedup.py` — Movie deduplication logic (torrent_url + title/year merge)
- `src/cli/alerter.py` — Feed health tracking + SMTP alert

### src/webui/ (FastAPI web app)
- `src/webui/main.py` — Entry point: FastAPI app startup (Uvicorn)
- `src/webui/app.py` — FastAPI app factory + static file mounting
- `src/webui/routes.py` — JSON API route handlers (movies + news + export/import)
- `src/webui/filters.py` — Rating/genre filtering and year-section grouping logic
- `src/webui/enrichment.py` — On-demand OMDb enrichment; extracts and returns `imdb_id`
- `src/webui/static/index.html` — React shell (CDN-loaded)
- `src/webui/static/app.js` — React components (JSX via htm + Babel CDN)
- `src/webui/static/styles.css` — Application styles

### Root
- `config.yaml` — User configuration (DB URL, filtering rules, SMTP, news feeds, etc.)
- `requirements.txt` — Python dependencies (includes `feedparser`)
- `migrate_001_schema.sh` — Idempotent DB migration script: `ai_filtered_views` M5 schema changes + `movies.imdb_id` column

## Key decisions (links to ADRs)
- ADR-001: FastAPI as web framework (rendering approach superseded by ADR-004)
- ADR-002: SQLAlchemy with MySQL primary / SQLite fallback
- ADR-003: On-demand enrichment (user-triggered, not at ingestion time)
- ADR-004: React via CDN — no build step
- ADR-005: `src/cli/` + `src/webui/` + `src/common/` structure
- ADR-006: Three-process architecture — CLI Ingester + CLI Filter Processor + FastAPI Web UI
- ADR-007: Two-table design for AI-filtered news (`news_items` + `ai_filtered_views`)
- ADR-009: Export/import replaces Claude CLI for AI-filtered news (supersedes ADR-008)

## Edge cases handled
- RSS feed format changes: parser logs warnings for unparseable entries, does not crash
- Enrichment API timeout: returns error to user, does not block other operations
- SQLite concurrent access: acceptable since ingester runs briefly every ~2h
- Movie deduplication: handles both URL-exact matches and title+year fuzzy matches (merges qualities)
- Empty/malformed config: validation on load with clear error messages
- News dedup: `(url, feed_name)` unique constraint; duplicate items skipped silently on re-ingestion
- Filtered feed with no matches: valid state — all `matched_filter_id` remain null; nothing appears in filtered UI view
- Import payload not valid JSON: returns `400 Bad Request`; existing `ai_filtered_views` unchanged
- Import row with unknown `source_item_id`: discarded and logged; remaining valid rows still persist
- Import row missing `title` or `url`: discarded and logged
- Export for feed with no unread items: valid — returns empty `unread_items` array; still includes `context_items`
- `imdb_id` absent (movie not yet enriched): IMDb badge falls back to title+year search URL; RT badges use title search URL

## Known limitations
- No bulk enrichment — user must click per-movie "Refresh Ratings"
- Export/import is available for all news feed types; the `ai_filtered` type gate was removed
- In-browser JSX transform via Babel CDN adds ~1s to initial page load
- CDN-loaded React requires internet on first visit (cached after)
- No Alembic migrations — schema changes require `migrate_001_schema.sh` or manual `ALTER TABLE`
- No authentication (localhost-only, single user)
- RT direct-page links not available (OMDb does not return an RT URL); RT badges always use search

## Migration steps (M1–M5, MySQL)

On a fresh DB: `create_all()` on startup creates all tables automatically — no manual steps needed.

On an existing DB (upgrading from M1–M4):

```bash
bash migrate_001_schema.sh
```

This script (idempotent — safe to re-run) applies:
1. `ai_filtered_views`: drops old `category_id` FK + column; renames `news_item_id` → `source_item_id`; swaps unique index name; renames `last_filtered_at` → `ingested_at`; adds `title`, `url`, `published_at`, `category` columns
2. `movies`: adds `imdb_id VARCHAR(20) NULL` column

## How to test locally

1. Install: `pip install -r requirements.txt`
2. Copy config: `cp config.yaml.example config.yaml` — edit DB URL and preferences
3. Run ingester: `python src/cli/main.py` — fetches movie RSS + all news feeds
4. Run filter processor: `python src/cli/filter.py` — regex-flags `filtered` feed items
5. Run web app: `python src/webui/main.py` — starts FastAPI on configured host:port
6. Open `http://127.0.0.1:8080`:
   - **Movies tab:** verify list renders; toggle Filtered / All; click quality badges to open torrent; click IMDb/RT rating badges
   - **Movies enrichment:** click "Refresh Ratings" — verify ratings appear and IMDb badge becomes a direct link
   - **News tab:** verify each feed type renders; mark items as read
   - **AI-filtered feed:** click "Export Unread" — verify JSON downloads with `unread_items` + `context_items`; upload a valid import file — verify `ai_filtered_views` rows appear
   - **Raw sub-view:** toggle "Show Raw Items" on an AI-filtered feed — verify all `news_items` appear
7. Stop the feed source or wait 24h+ without ingesting — verify email alert fires

---

## M6 — Series Feed

### Scope
- `Series` DB table and SQLAlchemy model
- EZTV RSS fetcher + S##E## parser in `fetcher.py`
- Series deduplication (merge quality variants) in `dedup.py`
- Feed health + alerter extended to EZTV feed
- `GET /api/series`, `POST /api/series/{id}/read`, `POST /api/series/{id}/unread` routes
- Series tab in React frontend (title → season → episode grouping, IMDb link, torrent links)

### Files to touch
- `src/common/models.py` — add `Series` model
- `src/cli/fetcher.py` — add `fetch_series_feed()` for EZTV RSS; add title parser
- `src/cli/dedup.py` — add `dedup_series()` (merge qualities by title+season+episode)
- `src/cli/main.py` — call series fetcher + deduplicator; update feed health for EZTV
- `src/cli/alerter.py` — include EZTV feed in downtime check
- `src/webui/routes.py` — add series API endpoints
- `src/webui/static/app.js` — add Series tab component
- `config.yaml` / `config.yaml.example` — add `series_feed.url`

### Key decisions
- ADR-010: IMDb ID not in EZTV feed; UI uses IMDb title-search URL as fallback; `imdb_id` always null
- ADR-011: Quality variants as JSON array `[{"quality": "...", "torrent_page_url": "..."}]` on the series row

### Edge cases to handle
- Title contains no S##E## pattern → log and skip (V-027)
- `imdb_id` absent from RSS entry → store null; omit IMDb link in UI (ADR-010)
- Duplicate quality variant on re-ingestion → merge (union by `quality` value; V-025)
- EZTV feed unreachable → update `feed_health`, do not crash; alert after 24h (FR-043, FR-047)
- Season 0 / episode 0 entries (specials) → store as-is; valid per V-022/V-023

### Feed inspection findings (Q-009, Q-010, Q-011 resolved)
- **Q-009:** EZTV title format is `Show Name S##E## quality encoder` (space-separated) or `Show.Name.S##E##.quality` (dot-separated). Torrent page URL is in `<link>`. No IMDb ID element exists in the feed.
- **Q-010:** Entries without S##E## pattern are logged and skipped (V-027). One skipped per ~30 entries observed in practice.
- **Q-011:** EZTV does not provide an IMDb ID. `imdb_id` is always stored as null. The UI falls back to an IMDb title-search URL for every series entry.

### Migration steps (M6)
- Fresh DB: `create_all()` on startup creates `series` table automatically
- Existing DB: manual `ALTER TABLE` or new `migrate_002_series.sh` idempotent script

### How to test locally (M6)
1. Run ingester: `python src/cli/main.py` — verify `series` table populated from EZTV feed
2. Open web app → Series tab — verify grouping by title → season → episode
3. Confirm multiple quality variants of same episode appear as separate links in one row
4. Confirm series title links to IMDb (where `imdb_id` is not null)
5. Simulate EZTV feed down → verify email alert fires after 24h

---

## M7 — Series Two-Table Split + Ignore

### Scope
- `series` table: one row per unique title (PK = `series.id`, `title` UNIQUE, `imdb_id` nullable, `is_ignored` bool)
- `series_episodes` table: one row per `(series_id, season, episode)`; FK → `series.id`; carries `qualities`, `feed_entry_date`, `ingested_at`, `is_read`
- Two-level deduplication in ingester: upsert series title row first (`session.flush()` to get PK), then upsert episode row
- `is_ignored` is a title-level flag on `series`; new episodes for an ignored series inherit via JOIN at query time — no per-episode flag needed
- `GET /api/series?view=unread|all|ignored` — three views (ADR-012)
- `POST /api/series/{series_id}/ignore` and `/unignore` — PK-based, O(1) single-row update
- `POST /api/series/episodes/{episode_id}/read` and `/unread` — episode-level read tracking
- `POST /api/series/read-all` — marks all `series_episodes.is_read`
- Series tab: Unread / All / Ignored view switcher; Ignore/Unignore per series title; Mark All Read hidden on Ignored view
- `clear_db.sh`: updated to detect old M6 single-table `series` schema, drop it, and call `init_db`; skips missing tables gracefully

### Files changed
- `src/common/models.py` — replaced old `Series` model with `Series` (title-level) + `SeriesEpisode` (episode-level)
- `src/cli/dedup.py` — rewrote `deduplicate_and_store_series` with two-level upsert
- `src/webui/routes.py` — rewrote all series endpoints; added `quote_plus` import for IMDb URL construction
- `src/webui/static/app.js` — updated `SeriesTab`: view names, API paths, ignore/unignore using series `id`
- `clear_db.sh` — migration-aware clear script

### Key decisions (ADR-012)
- `is_ignored` lives on `series` row (title level), not repeated on every episode; ignore/unignore is O(1)
- New episodes for an ignored series automatically "inherit" ignored status at query time via JOIN — no flag to propagate at insert time
- `imdb_url` now always returned in API response (search URL fallback when `imdb_id` is null, per ADR-010)
- Migration path: `clear_db.sh` auto-detects old schema and drops it; `init_db` creates new tables

### Migration steps (M7)
Run `clear_db.sh` from the project root — it detects the old single-table schema and handles the migration automatically:
```bash
bash clear_db.sh
python src/cli/main.py  # repopulate from live feed
```

### How to test locally (M7 + Series Two-Toggle)
1. Run `bash clear_db.sh && python src/cli/main.py`
2. Start web app → Series tab → default is Unread + Not-Ignored — confirm episodes grouped by title → season → episode
3. Click "Ignored" toggle — confirm view switches to ignored series (empty if none ignored yet)
4. Click "Not-Ignored" toggle — confirm back to not-ignored unread episodes
5. Click "Ignore" on a series — confirm it disappears from Not-Ignored view; switch to Ignored toggle to see it there
6. In Ignored view, click "Unignore" — confirm it moves back; switch to Not-Ignored to see it
7. Click "Read" toggle — confirm only read episodes appear; each row has "Mark Unread" button
8. Click "Mark Unread" on an episode — confirm it disappears from Read view; appears in Unread view
9. Back on Unread + Not-Ignored: click "Mark Read" on an episode — confirm it disappears from view
10. Click "Mark All Read" — confirm only the visible group (Not-Ignored OR Ignored) episodes are cleared
11. Run ingester again with an ignored series in DB — confirm new episodes do not appear in Not-Ignored views

---

## M8 — Movies Two-Toggle View

### Scope
- Replace the `view=...` param on `GET /api/movies` with two independent bool params: `read` (default `false`) and `flagged` (default `true`)
- `POST /api/movies/read-all` gains a `flagged` bool param — scopes which unread movies are marked read to the currently visible Flagged or Un-Flagged set
- No schema change — the Flagged/Un-Flagged split is computed at runtime via existing `filter_movies()` logic; no `is_flagged` column added
- Movies tab: two independent toggle buttons in the toolbar:
  - **Unread / Read** — toggles `read` param (default: Unread)
  - **Flagged / Un-Flagged** — toggles `flagged` param (default: Flagged)
- "Mark All Read" button shown only when Unread is active; calls `POST /api/movies/read-all?flagged={current}`
- Terminology: "Flagged" replaces "Filtered"; "Un-Flagged" replaces "Non-Filtered"

### Files to touch
- `src/webui/routes.py` — update `get_movies()`: replace `view` param with `read: bool` + `flagged: bool`; update `mark_all_movies_read()` to accept `flagged: bool` and scope the DB update accordingly
- `src/webui/static/app.js` — update `MoviesTab`: replace four-button toggle with two independent toggle buttons; update fetch URL; update "Mark All Read" call to pass `flagged` param

### Key decisions
- Two independent bools (`read`, `flagged`) instead of a single `view` enum — cleaner for combinable toggles and independently queryable
- "Mark All Read" scoped to current Flagged/Un-Flagged state — user can clear only the visible pile without affecting the other group
- No `is_flagged` column stored — thresholds are config-driven and change over time; storing the result would create stale data on every config edit
- Flagged/Un-Flagged computed as: fetch all movies for the given `read` state → run `filter_movies()` → return matching set (Flagged) or complement (Un-Flagged)

### How to test locally (M8)
1. Open Movies tab — confirm default is Unread + Flagged, movies grouped by year
2. Click "Un-Flagged" toggle — confirm only unread movies that fail the rating/genre filter appear
3. Click "Read" toggle (while on Flagged) — confirm only read movies that pass the filter appear
4. Click "Un-Flagged" toggle (while on Read) — confirm only read movies that fail the filter appear
5. From Unread + Flagged, mark a movie as read — confirm it disappears; switch to Read + Flagged to see it there
6. Click "Mark All Read" on Unread + Flagged — confirm only Flagged unread movies disappear; Un-Flagged unread movies remain
7. Click "Mark All Read" on Unread + Un-Flagged — confirm only Un-Flagged unread movies disappear
8. Verify "Mark All Read" does not appear when Read toggle is active
9. Change a rating threshold in config.yaml and reload — confirm a movie moves between Flagged and Un-Flagged without any DB change

---

## M11 — Design Feed (Planned)

### Scope
- `DesignItem` SQLAlchemy model + `design_items` table
- Design feed fetcher in `fetcher.py`: fetch + parse RSS/Atom via feedparser; extract `image_url` best-effort (priority: `media:content` → `enclosure` → first `<img>` in description HTML); strip HTML from summary; skip entries with no title or URL
- Design item deduplication in `dedup.py` (or inline in `main.py`): upsert by `(url, feed_name)` — skip if already stored
- Feed health + alerter extended to all `design_feeds` entries in config
- `GET /api/design`, `GET /api/design/{feed_name}/items`, `POST /api/design/items/{id}/read`, `POST /api/design/items/{id}/unread`, `POST /api/design/{feed_name}/read-all` routes
- Design tab in React frontend: per-feed selector; card layout (image left, title + summary right); Read/Unread toggle; per-item Mark Read/Unread; "Mark All Read" (Unread view only)
- `config.yaml` / `config.yaml.example`: `design_feeds:` block

### Files to touch
- `src/common/models.py` — add `DesignItem` model
- `src/common/config.py` — load `design_feeds` list
- `src/cli/fetcher.py` — add `fetch_design_feed()` + image extraction helper
- `src/cli/main.py` — call design fetcher for each configured feed; update feed health
- `src/cli/alerter.py` — include design feeds in downtime check
- `src/webui/routes.py` — add design API endpoints
- `src/webui/static/app.js` — add `DesignTab` component + per-feed card view
- `src/webui/static/styles.css` — add `.design-card`, `.design-image`, `.design-body` rules (mirroring movie card layout)
- `config.yaml` / `config.yaml.example` — add `design_feeds:` block

### Key decisions
- New `design_items` table rather than reusing `news_items` — `image_url` is a first-class column; avoids polluting news_items with a nullable column only design uses
- Image extracted from feed only — no HTTP scraping of the article page; null if not found in feed entry
- No filter/flagging — all items shown, no Flagged/Un-Flagged toggle
- No export — read/unread tracking only (unlike news feeds)
- Summary stored as plain text (HTML stripped at ingestion time)
- Multiple design feeds supported via `design_feeds:` list in config (same pattern as `news_feeds:`)
- Feed health + 24h alerting consistent with all other feeds

### Edge cases to handle
- Feed entry with no `<image>` / `<media:content>` / `<enclosure>` → `image_url = null`; card displays without image (FR-063)
- Feed entry with no summary/description → store empty string
- Duplicate `(url, feed_name)` on re-ingestion → skip silently (V-031)
- Design feed unreachable → update `feed_health`, do not crash; alert after 24h (FR-065, FR-066)
- `<img src>` in description that is a relative URL → store as-is; may not display correctly; acceptable given best-effort approach

### Migration steps (M11)
- Fresh DB: `create_all()` on startup creates `design_items` table automatically
- Existing DB: `design_items` table does not exist yet — `create_all()` will add it automatically on next startup (SQLAlchemy `create_all` is additive; existing tables untouched)

### How to test locally (M11)
1. Add `design_feeds:` block to `config.yaml` with Designboom URL
2. Run `python src/cli/main.py` — verify `design_items` table populated
3. Inspect a few rows: confirm `image_url` populated for items with feed images; null for those without
4. Start web app → Design tab → confirm cards render with image (when available), title linked to article, and summary
5. Toggle Read/Unread — confirm items move correctly; state survives app restart
6. Click "Mark All Read" — confirm view clears; switch to Read toggle to see items
7. Add a second design feed to config, re-run ingester — confirm both feeds appear in tab selector
8. Simulate design feed downtime → verify email alert fires after 24h

---

## M9 — News Feed Simplification + Read/Unread Toggle

### Scope
- **Removed**: `POST /api/news/{feed}/import` endpoint and Import UI button
- **Removed**: `GET /api/news/{feed}/raw` endpoint and raw sub-view in AI-filtered feeds
- **Removed**: `POST /api/news/views/{id}/keep` and `/unkeep` endpoints; Keep as Context buttons in UI
- `GET /api/news/{feed}/items` gains a `read: bool = Query(default=False)` param — returns only items matching `is_read == read`
- `GET /api/news/{feed}/export` simplified: returns only `unread_items` (no `context_items` section)
- All three feed views (`UnfilteredFeedView`, `FilteredFeedView`, `AIFilteredFeedView`) gain an **Unread/Read toggle** (default: Unread), identical pattern to Movies/Series
- Per-item "Mark Read" (Unread view) and "Mark Unread" (Read view) buttons **remove** the item from the current view on click instead of merely toggling its visual state
- "Mark All Read" button shown only in Unread state; marks all unread items for the feed; clears view
- `FeedToolbar` component simplified: Export button kept; Import button removed
- No DB schema changes — `keep_as_context` column left in place but unused

### Files to touch
- `src/webui/routes.py` — update `get_news_items()`: add `read` bool param; update export handler to drop `context_items`; delete import, raw, keep, unkeep route handlers
- `src/webui/static/app.js` — simplify `FeedToolbar` (remove Import); update all three feed view components with Read/Unread toggle; update `NewsItemRow` and `AIViewRow` to remove from view on click; remove `AIViewRow` Keep as Context button and `showRaw` logic

### Key decisions
- No DB migration needed — `keep_as_context` column is inert; leaving it avoids destructive ALTER TABLE on a live DB
- `ai_filter.sh` is broken by this change (import endpoint removed); script should be deleted or archived
- Export always exports unread `news_items` regardless of toggle state — the export is a workflow tool, not a view of the current UI state
- `read-all` for `ai_filtered` feeds marks `ai_filtered_views.is_read` only (not `news_items`); `news_items` for ai_filtered feeds are never shown in the UI after raw sub-view removal

### How to test locally (M9)
1. Open News tab → any feed → confirm default is Unread view (only unread items shown)
2. Click "Read" toggle — confirm only read items appear; each row has "Mark Unread" button
3. Click "Mark Unread" on an item — confirm it disappears from Read view; appears in Unread view
4. Back to Unread view: click "Mark Read" on an item — confirm it disappears from Unread view
5. Click "Mark All Read" — confirm Unread view empties; switch to Read toggle to see all items
6. Verify "Mark All Read" does not appear when Read toggle is active
7. Click "Export Unread" — confirm JSON contains only unread items (no `context_items` key)
8. Confirm no Import button appears anywhere in the News tab
9. For AI-filtered feed: confirm no "Show Raw Items" button and no Keep as Context button appear

---

## M12 — News List Layout + Date Grouping

### Scope
- `NewsItemRow` (shared by `UnfilteredFeedView` and `FilteredFeedView`): title now left-aligned and the "Mark Read"/"Mark Unread" button right-aligned on the same header row (`justify-content: space-between`); the per-item published-date line is removed
- `NewsFeedView` groups the (already server-sorted) item list by calendar day and renders one date header per group instead of a date on every row
- Date header labels: "Today" / "Yesterday" for the two most recent days, otherwise full `Weekday, Month D, YYYY`; items with no `published_at` are collected into a single trailing "Unknown date" group
- No change to sorting — `GET /api/news/{feed}/items` already returns `ORDER BY published_at DESC`; grouping is a render-time transform of the existing response
- Design tab (`DesignFeedView`) uses separate markup and is unaffected

### Files to touch
- `src/webui/static/app.js` — `NewsItemRow` markup restructured; new `newsDateKey`, `formatNewsDateLabel`, `groupNewsByDate` helpers; `NewsFeedView` render loop iterates date groups instead of a flat item list
- `src/webui/static/styles.css` — `.news-item-header` gains `justify-content: space-between`; new `.news-item-title-group` wraps title + filter badge; `.news-item-date` removed (no longer used); new `.news-date-section` / `.news-date-header` (sticky day header, same pattern as `.year-header`)

### Key decisions
- Grouping done client-side rather than via a new API shape — the API already returns items sorted by `published_at desc`, so a single pass over the response is sufficient and avoids an API contract change
- Undated items are pulled out of the normal day-boundary pass and always rendered as one trailing group, since NULL ordering position from the DB isn't guaranteed to be scattered predictably
- No DB/API/schema changes

### How to test locally (M12)
1. Open News tab → a feed with items spanning multiple days (Unfiltered or Filtered view)
2. Confirm each row shows the title on the left and Mark Read/Unread button on the right, on one line, with no per-row date text
3. Confirm items are grouped under date headers ("Today" / "Yesterday" / full date), each header shown once, items sorted descending by date/time within and across groups
4. Toggle to Read view — confirm the same grouping applies and "Mark Unread" still removes the row from the current view
5. If the feed has items with no `published_at`, confirm they appear together in one trailing "Unknown date" group

### Follow-up — Tighter Spacing
The original M12 spacing values were sized for a layout that still had a per-item date line; once that line was removed, the remaining padding/gap read as too loose. `src/webui/static/styles.css` values tightened (markup unchanged):
- `.news-item` padding: `1rem` → `0.6rem 1rem` (vertical only, horizontal unchanged)
- `.news-list` gap: `0.8rem` → `0.4rem`
- `.news-date-section` margin-bottom: `1.5rem` → `1rem`
- `.news-date-header` padding: `0.8rem 0 0.5rem` → `0.5rem 0 0.4rem`; margin-bottom: `0.8rem` → `0.5rem`

No markup, sorting, or grouping logic changes — pure CSS density pass.

---

## M13 — URL Hash Unique Keys (MySQL utf8mb4 Index-Length Fix)

### Scope
- Bug: MySQL rejected schema creation. `movies.torrent_url` (`VARCHAR(1000)`) had a `UNIQUE` constraint — under `utf8mb4` (4 bytes/char) that's a 4000-byte index key, over InnoDB's 3072-byte single-key-part limit, so `CREATE TABLE movies` failed outright
- Investigation found the identical defect on two more tables (confirmed with user, fixed together): `news_items` and `design_items` both had `UNIQUE (url VARCHAR(2000), feed_name)` — up to 9020 bytes. `movies` is created first, so it failed before the ingester ever reached those two tables, but they'd hit the same error next
- Fix: stop indexing the raw URL on all three tables. Added a `hash_url()` helper (SHA-256 hex digest, `CHAR(64)` = 256 bytes under utf8mb4) in `src/common/models.py`; each table gets a `*_hash` column and the unique constraint moves to the hash (`torrent_url_hash` alone for `Movie`; `(url_hash, feed_name)` for `NewsItem`/`DesignItem`, preserving the original per-feed dedup semantics)
- The raw URL columns (`torrent_url`, `url`) are unchanged in shape/length and remain unindexed — used only for storage/display/linking (movie quality links, article URLs)

### Files to touch
- `src/common/models.py` — `hash_url()` helper; `Movie.torrent_url_hash`, `NewsItem.url_hash`, `DesignItem.url_hash` columns; index definitions updated (`ux_movies_torrent_url_hash`, `ix_news_items_url_hash_feed`, `ix_design_items_url_hash_feed`)
- `src/cli/dedup.py` — `deduplicate_and_store`: existing-movie lookup now filters on `Movie.torrent_url_hash` instead of `Movie.torrent_url`; sets `torrent_url_hash=hash_url(...)` on insert
- `src/cli/main.py` — `_store_news_items`/`_store_design_items`: existing-item lookup now filters on `*.url_hash` instead of `*.url`; sets `url_hash=hash_url(url)` on insert (both the main insert and the per-item `IntegrityError` retry fallback)
- `tools/migrate_006_url_hash_unique_keys.sh` — new idempotent migration (see below)
- `docs/03-architecture-data/Data-Contracts.md` — schema blocks, index lists, V-009 updated; new "URL hash unique keys" subsection explaining the pattern

### Key decisions
- SHA-256 chosen for the hash — MySQL's built-in `SHA2(col, 256)` produces the exact same hex digest as Python's `hashlib.sha256(...).hexdigest()`, so the migration's SQL backfill and the app's `hash_url()` never disagree
- `CHAR(64)` (hex digest) rather than `BINARY(32)` (raw bytes) — slightly larger but trivially inspectable/debuggable in a DB client, and 256 bytes is nowhere near the 3072-byte limit either way
- Composite unique key kept as `(hash, feed_name)` for `NewsItem`/`DesignItem`, not hash-alone, to preserve the existing "same URL can exist in two different feeds" semantics
- On MySQL, the migration drops the old oversized unique index after adding the new one (found dynamically via `information_schema.STATISTICS`, not a hardcoded name) — safe because a table that never successfully finished `CREATE TABLE` (this user's reported failure case) simply has no such index to find, and the step no-ops
- On SQLite, the old inline unique constraint (if a table already existed there) is left in place rather than rebuilt away — SQLite has no index-key-length limit, so it's harmless, and rebuilding a table to drop an inert constraint isn't worth the risk on a live DB (same reasoning as M9's `keep_as_context` column)
- No behavior change to any read/write path other than the lookup column — `torrent_url`/`url` are still stored and returned exactly as before

### How to test locally (M13)
1. Fresh MySQL: run `python src/cli/main.py` — confirm `init_db()`/`create_all()` succeeds (no "index key too long" error) and `movies`/`news_items`/`design_items` are created with the new hash columns/indexes
2. Existing MySQL/SQLite DB: run `tools/migrate_006_url_hash_unique_keys.sh` — confirm it adds and backfills the three `*_hash` columns, and re-running it is a no-op (idempotent)
3. Verify row counts are unchanged before/after the migration (no data loss)
4. Re-run the ingester against already-ingested data — confirm no duplicate rows are created (hash-based lookup finds the existing record)
5. Confirm the web UI still renders Movies/News/Design and that movie quality links (which use `torrent_url` directly) still work

---

## M14 — full_content LONGTEXT (MySQL Data-Too-Long Fix)

### Scope
- Bug: ingestion crashed with `pymysql.err.DataError: (1406, "Data too long for column 'full_content'")`. `NewsItem.full_content` was plain SQLAlchemy `Text`, which compiles to MySQL `TEXT` — capped at 65,535 bytes. `full_content` stores the raw `<content>` HTML some feeds provide (not a summary), and the failing article (Visual Capitalist feed) was 115,000+ characters
- Checked every other `Text` column in `models.py` for the same risk: all are either short by construction (JSON-encoded `qualities`/`genres`, `Filter.pattern`, error messages) or explicitly HTML-stripped summaries populated from RSS `<summary>` (`Movie.plot`, `DesignItem.summary`) rather than a raw full-content dump — none carry the same risk profile, none reported failing. Fix scoped to `full_content` only
- Fix: `full_content` now uses `Text().with_variant(LONGTEXT(), "mysql")` — SQLAlchemy's per-dialect type override. MySQL gets `LONGTEXT` (4 GiB limit); SQLite (and any other backend) keeps plain `TEXT`, which is already unbounded there
- No application code changes needed — `Mapped[str]` type is unchanged, so `fetcher.py`, `main.py`, `routes.py`, `app.js` are untouched

### Files to touch
- `src/common/models.py` — `NewsItem.full_content` column type; new `from sqlalchemy.dialects.mysql import LONGTEXT` import
- `tools/migrate_007_full_content_longtext.sh` — new idempotent migration (MySQL only; SQLite is a no-op since it has no column-type change to make)
- `docs/03-architecture-data/Data-Contracts.md` — `full_content` field comment updated

### Key decisions
- `Text().with_variant(LONGTEXT(), "mysql")` over a raw dialect branch in application code — SQLAlchemy's standard mechanism for "different column type per backend," keeps the model as the single source of truth, no `if mysql: ... else: ...` scattered elsewhere
- Migration checks the live column's `information_schema.COLUMNS.DATA_TYPE` rather than assuming it needs altering — safe to re-run, and a table that doesn't exist yet (fresh install) is skipped since `create_all()` will create it correctly from the updated model
- Scoped to `full_content` only, not a blanket TEXT→LONGTEXT pass over every column — the other `Text` columns don't share the "arbitrary raw HTML from an external feed" risk profile that caused this specific failure

### How to test locally (M14)
1. Run `tools/migrate_007_full_content_longtext.sh` against an existing MySQL DB — confirm it alters `news_items.full_content` to `LONGTEXT`, and re-running it is a no-op (idempotent)
2. Insert (or re-ingest) a news item with a `full_content` value over 65,535 bytes — confirm it inserts without `DataError` and round-trips at full length
3. Confirm the web UI News tab still loads existing items after the `ALTER TABLE`

---

## M15 — News Feed Tag-Grouping (ADR-016)

### Scope
- Feature request: group `news_feeds` into tabs by a new `tag` config field, since the flat feed-picker row doesn't scale as feeds are added
- Fully specified during the docs pass before any code was written: FR-090–FR-094, AC-039–AC-043, Data-Contracts.md's `GET /api/news` contract, and ADR-016 (which also records the deliberate URL-scheme break, see below)
- Config-only feature — no DB schema change, no CLI/ingester change. `tag` is read from `config.yaml` at request time by the web UI only, the same treatment as the existing `type`/`filters` fields

### Files touched
- `config.yaml` / `config.yaml.example` — new `news_tag_priority` ordered list; `tag:` added to every `news_feeds` entry (first-draft categorization — trivially hand-editable, not meant to be a firm taxonomy)
- `src/webui/routes.py` — `get_news_feeds()` now defaults missing `tag` to `"General"` and pre-sorts the returned `feeds` array by tag-priority order before returning it; `serve_spa_route` decorators extended with `/news/{tag}` and `/news/{tag}/{feed_name}`, replacing the old `/news/{feed_name}`
- `src/webui/static/app.js` — `parseLocation()` branches on `tab === "news"` to parse a 3-segment path (`{tag}/{feed_name}`) instead of the generic 2-segment form still used by Design; `App()` passes `initialTag` through to `NewsTab`; `NewsTab` restructured into two levels (tag-tab row + the existing per-feed row, now scoped to the active tag)
- `src/webui/static/styles.css` — new `.news-tag-nav`/`.tag-nav-btn` rules; `.news-feed-nav` top padding trimmed now that it sits below the tag row

### Key decisions
- Tag-priority sorting is done **once, server-side**, in `get_news_feeds()` — mirrors the existing `sort_by_genre_priority` pattern in `src/webui/filters.py` (priority list → `{value: index}` map, unlisted values appended via an incrementing counter, Python's stable `sort()` preserves original relative order for ties). The client only needs to group the already-ordered array by `tag`; it never sees `news_tag_priority` itself, so there's no second endpoint or extra config exposed to the frontend
- The "old link falls back to default" requirement (FR-094/AC-042) needed no special-case code: `NewsTab`'s initial-load resolution logic already validates `activeTag`/`activeFeed` against the fetched feed list and falls back to the first tag/first feed if either doesn't match. An old-style `/news/{feed_name}` link parses (`parseLocation`) as `tag = feed_name`, which — being some arbitrary feed name, not a real tag — simply fails that validation and falls through to the same default-selection path used on a bare `/news` visit
- `serve_spa_route` accepts both `tag` and `feed_name` as optional params across all its decorators (some routes only supply one or neither) — consistent with the pre-existing "accepted but unused server-side" comment, since the SPA shell is identical regardless of path

### How to test locally (M15)
1. `GET /api/news` — confirm each feed dict includes `tag` and the array is grouped/ordered per `news_tag_priority` (tags not in that list appended after, in first-appearance order)
2. Load `/news` — confirm it lands on the first tag tab and that tag's first feed, matching the auto-select behavior that existed pre-feature for the single-feed-row case
3. Click through tag tabs — confirm the feed row below updates to that tag's feeds only, the first feed auto-selects, and the URL updates to `/news/{tag}/{feed}` without a page reload
4. Visit `/news/{tag}` directly — confirms that tag's first feed loads
5. Visit an old-style `/news/{feed_name}` link — confirms it falls back to the default tag/feed instead of erroring or 404ing
6. Browser back/forward across tag and feed changes — confirms `popstate` restores the right tag+feed combination
7. Confirm Design tab is unaffected — still a flat feed picker, `/design/{feed_name}` unchanged

---

## M16 — Saved Entries (ADR-017)

### Scope
- Feature request: a cross-feed "bookmark" mechanism — save any item from any of the four content tabs into one common-format table, browsable and exportable from a new Saved tab
- Fully specified during the docs pass before any code was written: FR-095–FR-103, AC-044–AC-050, Data-Contracts.md's `SavedEntry` schema/API contracts, and ADR-017 (records the single-common-table decision, the per-source-type field mapping, and the rejected alternatives)
- New `saved_entries` table + SQLAlchemy model
- New "Save Entry" action on every item: `POST /api/movies/{id}/save`, `POST /api/series/{series_id}/save` (title-level, not per-episode), `POST /api/news/items/{id}/save`, `POST /api/design/items/{id}/save` — all idempotent on `(source_type, source_id)`
- `is_saved` added to every existing list endpoint's item shape (`GET /api/movies`, `GET /api/series`, `GET /api/news/{feed_name}/items`, `GET /api/design/{feed_name}/items`)
- New `GET /api/saved`, `DELETE /api/saved/{id}`, `GET /api/saved/export` endpoints
- New Saved tab in the React frontend: flat list ordered by `saved_at` descending, "Remove from Saved" per row, "Export" button; new `/saved` route
- No CLI/ingester or Filter Processor changes — this is Web UI-only, populated by user action, not by ingestion

### Files changed
- `src/common/models.py` — added `SavedEntry` model (`saved_entries` table) with a unique index on `(source_type, source_id)` and a secondary index on `saved_at`; no FK (spans four parent tables)
- `src/webui/routes.py` — added `_movie_imdb_url()` (mirrors the client-side IMDb URL fallback in `MovieCard`, used only internally by the save path — not exposed on `GET /api/movies`, whose response shape is unchanged) and extracted `_series_imdb_url()` out of `_build_series_response` (now shared with the series save path); added `_movie_save_fields`/`_series_save_fields`/`_news_save_fields`/`_design_save_fields` (FR-096 per-type mapping), `_get_or_create_saved_entry` (idempotent get-or-create, the first such helper in this codebase), `_saved_entry_to_dict`, and `_saved_source_ids` (one query per list request feeding `is_saved`); added the four `POST .../save` handlers next to their sibling read/follow endpoints; added `is_saved` to `_movie_to_dict`, `_build_series_response`, and the News/Design item dict literals; added `GET /api/saved`, `DELETE /api/saved/{id}`, `GET /api/saved/export`; extended `serve_spa_route` with `/saved`
- `src/webui/static/app.js` — added shared `SaveButton` component (loading state + fetch + `onSave` callback that flips `is_saved` in place rather than removing the item, unlike every existing action button); wired into `MovieCard` (`.movie-actions`), the `SeriesTab` title row (unconditionally, not gated by `category` — the one row-level action that isn't), `NewsItemRow` (`.news-item-header`), and `DesignItemCard` (`.design-actions`), each with a matching `handleSaveEntry` state updater in its parent tab component; added `SavedTab` component (fetch on mount, Remove via `DELETE`, Export via `window.location.href`); added `"saved"` to `TABS`, a 5th tab button, and the `SavedTab` dispatch branch in `App()`
- `src/webui/static/styles.css` — added `.btn-save`/`.btn-saved` (modeled on `.btn-keep`/`.btn-keep-active`), `.series-save-btn` (distinct from `.series-ignore-btn` since Save isn't category-gated), and `.saved-summary`; the Saved tab's list otherwise reuses `.news-list`/`.news-item`/`.news-item-header`/`.empty-state` as-is
- `tools/migrate_008_saved_entries.sh` — new idempotent migration creating the `saved_entries` table on an existing (already-deployed) DB, for anyone who doesn't want to wait for the next `create_all()`-on-startup

**Follow-up fix (Unreleased):** `.saved-summary` unbounded text was a readability problem in the flat Saved list — clamped to 2 lines via CSS `line-clamp`/`-webkit-line-clamp` with `overflow: hidden` (ellipsis on overflow), CSS-only, no JS change.

### Key decisions (ADR-017)
- One common `saved_entries` table across all four content types, not four separate per-type "saved" tables — matches the user's explicit ask for "a common format" and keeps the Saved tab a single flat list/export without a union query across four schemas
- `source_type` + `source_id` instead of a real FK — a single FK can't span four different parent tables; validity of `source_id` is checked at the application layer only, at save time
- Series saves at the **title level**, not per-episode — mirrors Follow/Ignore's granularity (series-level actions), avoids ambiguity over "which quality variant" a per-episode save would need to carry
- `link` for Movies/Series is the IMDb URL (reusing the exact value already computed for the title link), not a torrent/episode URL — points to a durable webpage rather than a torrent file, and sidesteps the "which quality variant" problem entirely
- `feed_name` for Movies/Series is a fixed string (`"Movies"`/`"Series"`) rather than sourced from config, since neither content type has a per-item config-driven feed name the way News/Design do
- Idempotent on `(source_type, source_id)`, not `(source_type, link)` — simpler, exact, and doesn't require re-hashing a URL; the frontend already has the source id on hand when rendering the button
- No read/unread tracking on `saved_entries` — Saved is a flat curated list; the only lifecycle action is Remove (delete), keeping the feature intentionally lightweight rather than duplicating the News/Design read-tracking pattern
- Saved export always includes every row (no unread-only filtering like the News export) — there's no read state to filter by, and the list is expected to stay small since Remove is available

### Edge cases to handle
- Save request for a `source_id` that doesn't exist (e.g. stale frontend state) → 404, no row created
- Save request for an already-saved `(source_type, source_id)` → return the existing row unchanged, no duplicate insert (V-043)
- Movie/Series with null `plot`/no synopsis → `summary` stored as empty string, never null (matches the FR-096 mapping)
- Remove from Saved on an already-removed `id` (e.g. double-click) → 404 is acceptable; frontend should already have removed the row from view after the first successful call
- Saved tab with zero entries → valid empty state, Export still works (returns `entries: []`)

### Migration steps (M16)
- Fresh DB: `create_all()` on startup creates `saved_entries` automatically — no manual step needed
- Existing DB (deployed instance, don't want to wait for the next app startup): `bash tools/migrate_008_saved_entries.sh` — creates `saved_entries` (with `ux_saved_entries_source` and `ix_saved_entries_saved_at`) via `SavedEntry.__table__.create(engine, checkfirst=True)` rather than hand-written `CREATE TABLE` SQL, so it's correct for both MySQL and SQLite from the model definition and needs no dialect branching. Idempotent — re-running after the table already exists (including one created by `create_all()` itself) is a no-op. No data backfill — brand-new table, nothing to migrate from. Verified against the live MySQL dev DB (drop → run → schema/indexes confirmed correct → re-run confirmed no-op) and against a fresh SQLite file (create + idempotent re-run, both confirmed via direct `SavedEntry.__table__.create()` calls matching what the script does).

### How to test locally (M16)
1. Start the web app; open Movies, Series, News, and Design tabs — confirm every item/row shows a "Save Entry" button alongside its existing actions, regardless of Read/Unread (or Series category) state
2. Click "Save Entry" on one item of each type — confirm the button immediately becomes a disabled "Saved" state with no page reload
3. Reload the page — confirm the same items still show "Saved" (driven by `is_saved` in the list response, not just client-side click state)
4. Open the Saved tab — confirm all four saved items appear together in one flat list, most-recently-saved first, with no read/unread or filter toggle
5. Click "Save Entry" again on an already-saved item (e.g. via a direct API call) — confirm no duplicate row appears in the Saved tab
6. Click "Remove from Saved" on one entry — confirm it disappears from the Saved tab immediately, and its button on the original tab (Movies/Series/News/Design) becomes clickable again after a refetch
7. Click "Export" on the Saved tab — confirm a JSON file downloads containing every remaining saved entry
8. Confirm the Movies/Series/News/Design source rows themselves are unaffected by any Save/Remove action (read status, category, etc. unchanged)
9. Visit `/saved` directly — confirm it loads with the Saved tab active

**Verified:** steps 1-2 and 5-9 above were run directly against the API (`curl`) on the live MySQL dev DB — one real item of each of the four types was saved, `is_saved` confirmed `true` on a fresh `GET` (not just the save response), a second save on the same id confirmed idempotent (same `saved_entries.id`, single DB row via direct query), `GET /api/saved` returned all four grouped correctly (most-recent-first), `DELETE /api/saved/{id}` removed each and flipped the source item's `is_saved` back to `false` on the next `GET`, `GET /api/saved/export` returned a valid download (including the empty-list case after cleanup) with the `"Saved export: N items"` log line, `GET /saved` returned 200, and 404s were confirmed on all four save endpoints plus delete for a nonexistent id. Source rows' `is_read`/`is_following`/`is_ignored` were confirmed unchanged by direct DB query before/after. All test data was cleaned up afterward (`saved_entries` empty, matching pre-test state). **Not verified in this pass:** the actual React UI in a browser (button rendering/disabled-state styling, click interactions, tab navigation) — this environment has no GUI browser available, so the frontend was verified by code review and JS syntax check (`node --check`) only, not a live click-through.

---

## M17 — Mark Day as Read (News)

### Scope
- Feature request: a per-date-section "Mark day as Read" button on the News tab, scoped only to the items already grouped under that date header (including the trailing "Unknown date" group for undated items) — not the whole feed like the existing "Mark All Read" (FR-050)
- New endpoint: `POST /api/news/{feed_name}/read-day`, accepting a JSON body of `item_ids`
- New frontend component `NewsDateSection` wrapping each date group, owning its own "marking" loading state and rendering the button only on the Unread toggle
- No DB schema change, no CLI/ingester change — pure Web UI read-tracking addition, same table (`news_items`) and column (`is_read`) as the existing read/unread actions

### Files changed
- `src/webui/routes.py` — added `from pydantic import BaseModel`; added `NewsItemIdsRequest` (`item_ids: list[int]`) and `POST /api/news/{feed_name}/read-day`, placed directly after `mark_all_news_read`; reuses `_get_news_feed_cfg` for the 404-on-unknown-feed check
- `src/webui/static/app.js` — extracted the previously-inline per-group render block out of `NewsFeedView` into a new `NewsDateSection` component (mirrors the existing per-row loading-state pattern used by `MovieCard`/`NewsItemRow`); `NewsFeedView` now maps `groupNewsByDate(items)` to `<NewsDateSection>` instead of rendering the group markup directly
- `src/webui/static/styles.css` — split `.news-date-header` into `.news-date-header-row` (the sticky/border/padding/background/z-index flex wrapper, now holding both the label and the button) and a slimmed-down `.news-date-header` (text styling only)

### Key decisions
- **Item-id list, not a date query param** — the day boundaries used to build each group ("Today"/"Yesterday"/full date, and the "Unknown date" bucket) are computed client-side from the browser's local clock (`newsDateKey`/`formatNewsDateLabel`). The server has no reliable way to reproduce the same boundary (no stored user timezone), so replicating "mark everything published on date X" server-side risked marking a different set of items than what the user was actually looking at. Submitting the exact ids already rendered in that group sidesteps the mismatch entirely, and naturally covers the undated "Unknown date" group where a date-based query wouldn't apply anyway.
- **Scoped by `feed_name` + `id IN (...)`, not id-only** — defends against a stale or tampered id list from marking items in a different feed as read.
- Ids that are already read, or don't belong to `feed_name`, are silently excluded from the update (not an error) — the endpoint returns `marked: <n>` reflecting only the ids that actually flipped, consistent with the fire-and-forget style of `read-all`.

### Edge cases to handle
- Empty `item_ids` list (e.g. a group already emptied by a race with another tab) → endpoint short-circuits to `{"ok": true, "marked": 0}`, no query executed
- Id list containing an id from a different feed → filtered out by the `feed_name` clause, not marked, not errored
- Id list containing an already-read id (e.g. double-click before the UI removes the row) → excluded by `is_read == False` in the filter, doesn't affect the `marked` count
- Unknown `feed_name` → 404 via `_get_news_feed_cfg`, same as every other News endpoint

### How to test locally (M17)
1. `python -c "import ast; ast.parse(open('src/webui/routes.py').read())"` and `node --check src/webui/static/app.js` — syntax sanity check, no GUI browser in this environment (same limitation noted in M16)
2. Start the web app; open a News feed with unread items spanning two or more days (plus at least one undated item, if available, to exercise "Unknown date")
3. Confirm each date header shows a "Mark day as Read" button only while the Unread toggle is active
4. Click it on one date section — confirm only that section's items disappear from view, and unread counts for other date sections and other feeds are unaffected
5. Switch to the Read toggle — confirm the button is absent
6. `curl -X POST http://127.0.0.1:8000/api/news/{feed}/read-day -H "Content-Type: application/json" -d '{"item_ids": [...]}'` with a mix of valid unread ids, an already-read id, and an id from a different feed — confirm `marked` counts only the valid unread ids for that feed, and a follow-up `GET /api/news/{feed}/items?read=true` shows them moved

---

## M18 — News Export Follows Active View

### Scope
- Feature request: the News tab's Export button ("Export Unread") always exported unread items regardless of which Read/Unread toggle was active. Changed so Export downloads whichever view is currently open.
- While reviewing the export path, found a pre-existing gap: for `filtered`-type feeds, export ignored `matched_filter_id`, so it included unread items that never matched a filter and are never shown in that feed's own view. Fixed at the same time, per user decision, so export exactly mirrors `GET /api/news/{feed_name}/items` for the same `read`/feed-type combination.
- Three explicit user decisions (asked via clarifying questions before implementation):
  1. Rename the export JSON's `unread_items` key to `items`, add an `is_read` field — safe because the import feature that once consumed this format was removed in ADR-009 (M9).
  2. Button label changes to static "Export View" (not dynamic per toggle).
  3. Fix the filtered-feed `matched_filter_id` gap now rather than deferring it.
- No DB schema change, no CLI/ingester change — pure Web UI change to an existing read-only endpoint.

### Files changed
- `src/webui/routes.py` — `export_feed` gains a `read: bool = Query(default=False)` param; the query now filters `is_read == read` instead of hardcoding `False`, captures `feed_cfg = _get_news_feed_cfg(...)` (previously discarded) to read `feed_type`, and adds a `matched_filter_id != None` clause when `feed_type == "filtered"`; payload key renamed `unread_items` → `items`, with a new `is_read` field; log line now reports `"read"` or `"unread"` dynamically instead of always `"unread"`
- `src/webui/static/app.js` — `FeedToolbar` gains an `isRead` prop, used to build `.../export?read=${isRead}`; button label changed from "Export Unread" to "Export View"; `NewsFeedView`'s `<FeedToolbar>` call site passes its existing `isRead` state through (the only call site — verified no other component renders `FeedToolbar`)

### Key decisions
- **Query param over separate endpoints** — `?read=<bool>` mirrors the exact same parameter already used by `GET /api/news/{feed_name}/items?read=<bool>`, keeping the export endpoint's contract consistent with the list endpoint it's meant to mirror.
- **`items` key + `is_read` field over keeping `unread_items`** — `unread_items` would be actively misleading once the Read view can be exported too; renaming was judged safe specifically because the only other consumer of this export format (the import endpoint) was already removed (ADR-009), so there's no external format to stay backward-compatible with.
- **Filtered-feed fix bundled into this change** — the gap was only noticed because "export mirrors the view" forced a direct comparison against `get_news_items`'s filtering logic; fixing it separately later would leave export inconsistent with the view in the interim for filtered feeds specifically.
- **Static "Export View" label over dynamic "Export Unread"/"Export Read"** — explicit user choice; keeps the button's rendering simpler while still describing behavior (exports the view) accurately.

### Edge cases to handle
- `filtered`-type feed with zero matched items in the requested `read` state → `items: []`, valid empty export, no error
- `unfiltered`-type feed → unaffected by the new `matched_filter_id` clause (only applied when `feed_type == "filtered"`)
- Read view with zero read items yet (e.g. a feed nobody has marked read) → same empty-array behavior, not a 404 or error

### How to test locally (M18)
1. `python3 -c "import ast; ast.parse(open('src/webui/routes.py').read())"` and `node --check src/webui/static/app.js`
2. Start the web app; `curl "http://127.0.0.1:8080/api/news/{feed}/export?read=false"` and `?read=true` against a real feed — confirm `items`/`is_read` in the payload and that counts match the corresponding `GET /api/news/{feed}/items?read=<bool>` call
3. Repeat against a `filtered`-type feed — confirm every exported item has a non-null `matched_filter_id`, for both `read=false` and `read=true`
4. In the browser: toggle Unread/Read on a News feed, click "Export View" in each state, confirm the downloaded file's `items` matches what's on screen and `is_read` reflects the active toggle

**Verified:** ran directly against the live MySQL dev DB via `curl` — exported a real `unfiltered` feed (Tech News) at both `read=false` and `read=true`, confirmed the `items`/`is_read` shape (including the `unread_items` key being gone) and that counts matched `GET /api/news/{feed}/items?read=<bool>` exactly (42 unread, 8 read); also confirmed a 404 for an unknown feed name and the updated log line format. Export is a read-only `GET` with no side effects, so no test-data cleanup was needed. **Not verified live:** the `filtered`-type `matched_filter_id` restriction — the current `config.yaml` has no `filtered`-type feed configured, and temporarily editing the live config to fabricate one was judged too risky for a running instance. This path was verified by code review only: it's the identical `matched_filter_id != None` conditional already exercised in production by `get_news_items` for the `filtered` branch, applied to the same query pattern.

---

## M19 — Movie Title Links to Source Page

### Scope
- Feature request: swap the Movies tab's title/IMDb-rating link assignment. Previously the movie **title** linked to IMDb (FR-038) and the IMDb rating badge was plain text; now the title links to the movie's own source page (the RSS feed entry's own page link) and the IMDb rating badge is the clickable IMDb link instead, matching how the RT/Audience badges already work.
- Investigation found `Movie.torrent_url` — confirmed by querying the live dev DB — is a direct `.torrent` file download link (e.g. `https://yts.gg/torrent/download/...`), not a page/article. The actual YTS movie page is the RSS entry's own `<link>`, which `fetcher.py` discarded whenever an enclosure was present (which YTS entries always have). No source-page URL was stored anywhere before this milestone.
- User-confirmed decision (asked via clarifying question, given the schema-change implication): add a new nullable `movies.source_url` column, populated from the RSS entry's `<link>` unconditionally, with a migration script. Existing rows stay `NULL` until re-ingested.
- Title link fallback for `source_url IS NULL` rows: falls back to `torrent_url` (a judgment call, not separately asked — chosen because it always yields a working link, same graceful-degradation spirit already used elsewhere, e.g. the IMDb search-URL fallback when `imdb_id` is unknown).

### Files changed
- `src/common/models.py` — added `Movie.source_url` (`String(1000)`, nullable), placed next to `torrent_url_hash`
- `src/cli/fetcher.py` — `_parse_entry` now captures `entry.get("link") or None` unconditionally into a new `source_url` var (previously `entry.get("link", "")` was only consulted as a `torrent_url` fallback when no `<enclosure>` was present), added to the returned dict
- `src/cli/dedup.py` (`deduplicate_and_store`) — new-insert branch passes `source_url=movie.get("source_url")` to the `Movie(...)` constructor; both merge branches (matched by `torrent_url_hash` and by title+year) opportunistically backfill `existing.source_url` from the incoming `movie.get("source_url")` when the existing row doesn't have one yet, so already-ingested movies pick this up the next time the feed re-lists them
- `src/webui/routes.py` — `_movie_to_dict` adds `"source_url": movie.source_url`
- `src/webui/static/app.js` — `MovieCard`'s title anchor changed from `imdbUrl` to `movie.source_url || movie.torrent_url`; the `imdbUrl` computation (unchanged) is now passed as `href` to the IMDb `RatingBadge` call instead, reusing the same optional-`href`-wrapping behavior `RatingBadge` already implements for the RT/Audience badges (including the existing N/A-stays-plain-text short-circuit) — no changes needed to `RatingBadge` itself
- `tools/migrate_009_movie_source_url.sh` — new idempotent migration adding the nullable column (MySQL/SQLite branch, `information_schema`/`PRAGMA` existence check), following the `migrate_004_movie_runtime_plot.sh` pattern

### Key decisions
- **New column over reusing `torrent_url`** — `torrent_url` is a direct download link, not a page; conflating the two would make the title link to the same download file the quality badges already link to, losing the actual source-page destination entirely.
- **Unconditional capture in the fetcher, not just a fallback** — the old logic only ever looked at `entry.get("link")` when there was no enclosure, so for YTS (which always has one) this value was never observed before. Capturing it as its own field regardless of enclosure presence is what makes the source page available at all.
- **No historical backfill** — the original `<link>` values for already-ingested movies were never stored anywhere and can't be recovered retroactively; the opportunistic backfill in `dedup.py`'s merge branches is the only path old rows have to eventually get `source_url` populated (next time the feed still lists them).
- **Fallback to `torrent_url`, not to a dead link or no link at all** — keeps every movie's title clickable even before re-ingestion catches up.

### Edge cases to handle
- Movie row with `source_url IS NULL` (not yet re-ingested) → title falls back to `torrent_url`, still clickable
- Movie with `imdb_rating IS NULL` (unenriched) → IMDb badge renders as plain "IMDb: N/A" text, same as before — `RatingBadge`'s existing early-return on null value means the new `href` is never consulted in this case
- RSS entry with `<link>` present but empty string → `entry.get("link") or None` normalizes empty string to `None`, keeping the nullable column's semantics consistent (no empty-string vs NULL ambiguity)
- Existing merge path (same `torrent_url_hash` or same title+year) where the existing row already has a `source_url` → backfill check (`if not existing.source_url`) is a no-op, never overwrites an already-populated value

### How to test locally (M19)
1. `python3 -c "import ast; ast.parse(open('src/common/models.py').read())"` (and the same for `fetcher.py`, `dedup.py`, `routes.py`); `node --check src/webui/static/app.js`
2. `bash tools/migrate_009_movie_source_url.sh` against the live dev DB — confirm the column is added, confirm a second run reports "already exists"
3. Run the CLI ingester once (`python src/cli/main.py`) to pull fresh YTS entries; query the DB directly to confirm at least one movie row has a non-null `source_url` distinct from its `torrent_url`
4. Start the web app, open the Movies tab: confirm the title now opens a movie page (not IMDb) in a new tab, and the IMDb rating badge is now clickable (opens IMDb) when a rating is present; confirm it stays plain text for an unenriched (N/A) movie; confirm RT/Audience badges are unchanged
5. Find a movie row with `source_url` still `NULL` (pre-migration data untouched by a subsequent ingest) — confirm its title falls back to the torrent link rather than being broken

**Verified:** ran `tools/migrate_009_movie_source_url.sh` against the live MySQL dev DB (added the column, confirmed idempotent on re-run), then confirmed via direct `GET /api/movies` calls: pre-migration rows correctly show `source_url: null` (e.g. movie id 7/9) alongside `torrent_url` still populated; the scheduled cron ingester (runs every 2 hours independently of this session) had already picked up the code change by the time this was checked and produced at least one real row with a populated `source_url` distinct from `torrent_url` (movie id 28, `https://yts.gg/movies/achilles-returns-2026`), confirming the fetcher/dedup path works against the live feed unattended. All four Movies view combinations (`read`×`flagged`) were queried via the API and returned successfully post-migration. **Not verified live:** the actual click-through in a browser (title opening the source page, IMDb badge becoming clickable, N/A badges staying plain) — no GUI browser is available in this environment (same limitation noted in M16/M18); verified by code review instead, reusing `RatingBadge`'s existing, unmodified `href`-wrapping and N/A short-circuit logic. The current dataset also didn't happen to include a null-`imdb_rating` (N/A) movie in the unread/flagged view at verification time to visually confirm against, though the code path is unchanged from what M1–M18 already exercised.
