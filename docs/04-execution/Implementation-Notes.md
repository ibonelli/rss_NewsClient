# Implementation Notes — pelis-feed

## Scope implemented

All milestones M1–M8 are implemented and running in production.

- **M1 — Ingestion:** CLI ingester, RSS fetch/parse, dedup, storage
- **M2 — Enrichment:** On-demand OMDb enrichment via web UI; stores `imdb_id` for direct linking
- **M3 — Web Application:** FastAPI + React CDN frontend; movie list with Filtered/All toggle; rating badges link to IMDb/RT
- **M4 — Alerting + Polish:** Feed health tracking per feed; SMTP alert on 24h downtime
- **M5 — News Feeds + Filter Processor:** News ingestion (all types); CLI Filter Processor (regex only); News tab in web UI; export/import for AI-filtered feeds
- **M6 — Series Feed:** EZTV ingestion; Series tab with read-tracking; feed health + alerting
- **M7 — Series Two-Table Split + Ignore:** Split `series` into `series` (title-level) + `series_episodes` (episode-level); `is_ignored` on `series` row; three Series views (Unread/All/Ignored); Ignore toggle at series title level; ingester inherits ignored status on new episodes
- **M8 — Movies Two-Toggle View:** Replace Filtered/All toggle with two independent toggles — Read/Unread and Flagged/Un-Flagged

## Files touched

### src/common/ (shared components)
- `src/common/models.py` — SQLAlchemy models: `Movie`, `Series`, `SeriesEpisode`, `FeedHealth`, `NewsItem`, `Filter`, `AIFilteredView`
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
