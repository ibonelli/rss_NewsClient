# Change Log — pelis-feed

## Unreleased

### Planned — M7: Series Two-Table Split + Ignore
- `series` table: one row per unique title (`title` UNIQUE, `imdb_id` nullable, `is_ignored` bool)
- `series_episodes` table: one row per `(series_id, season, episode)`; FK → `series.id`; carries `qualities`, `feed_entry_date`, `ingested_at`, `is_read`
- Deduplication now two-level: upsert series title first, then upsert episode
- Ingester inherits `is_ignored` from parent series row when inserting new episodes
- New endpoints: `POST /api/series/{id}/ignore`, `/unignore`; `POST /api/series/episodes/{id}/read`, `/unread`
- `GET /api/series` gains `view` param: `unread` (default) | `all` | `ignored`
- `POST /api/series/read-all` now marks `series_episodes.is_read`
- Series tab gains Ignore toggle per title and view switcher (Unread / All / Ignored)
- Migration: none — use `clear_db.sh` then re-ingest

### Added — M7: Series Ignored Feature
- `series.is_ignored` boolean column (default `false`); title-level flag — toggling it updates every episode row sharing that title
- `GET /api/series?view=filtered|all|read` — three sub-views replacing the previous single unread-only list
  - `filtered` (default): unread AND not ignored
  - `all`: unread including ignored
  - `read`: all read entries; not-ignored titles listed before ignored titles
- `POST /api/series/ignore` and `POST /api/series/unignore` — title-level toggle endpoints; body `{"title": "…"}`; return affected row count
- CLI Ingester inherits ignored status: new episodes ingested for an already-ignored series title are stored with `is_ignored = true`
- Series tab gains three sub-tabs (Filtered / All / Read) and an Ignore/Unignore toggle button at the series title level
- `migrate_002_series_ignored.sh` — idempotent migration adding `is_ignored` column to existing DBs

---

### Changed — Export/Import universalised; Mark All Read added
- Export (`GET /api/news/{feed}/export`) and Import (`POST /api/news/{feed}/import`) now available for **all** news feed types, not just `ai_filtered`; `_get_ai_filtered_feed` type gate removed; raw endpoint (`GET /api/news/{feed}/raw`) similarly unrestricted
- `FeedToolbar` component (Export / Import Results / Mark All Read) now renders on every news feed view
- `POST /api/movies/read-all` — marks all unread movies as read; Movies tab toolbar gains "Mark All Read" button
- `POST /api/series/read-all` — marks all unread episodes as read; Series tab gains toolbar with count and "Mark All Read" button
- `POST /api/news/{feed}/read-all` — marks all `news_items` and `ai_filtered_views` for the feed as read

### Added — M6: Series Feed
- EZTV RSS ingestion (`https://eztv.re/ezrss.xml`) with S##E## parsing; handles both space- and dot-separated title formats
- `Series` DB table; deduplication merges quality variants by `title+season+episode`
- `GET /api/series` grouped by title → season → episode; IMDb search link per series title (EZTV feed has no IMDb ID); torrent page link per quality variant
- Read-tracking for series entries (`POST /api/series/{id}/read`, `/unread`)
- Feed health + email alerting extended to EZTV feed (`eztv_series`)
- `config.yaml` / `config.yaml.example`: `series_feed.url` key

### Added — UI / Enrichment improvements
- Movies tab: **Filtered / All toggle** — switches between rating-filtered view and full unread-movie list without page reload (`GET /api/movies?filtered=false`; FR-037)
- Movies tab: **IMDb rating badge** links directly to `https://www.imdb.com/title/{imdb_id}/` for enriched movies; falls back to IMDb title-search URL when `imdb_id` is not yet known (FR-038)
- Movies tab: **RT Tomatometer and Audience badges** link to Rotten Tomatoes search for the movie title (FR-038)
- Movies tab: **quality/resolution badges** (720p, 1080p, 2160p) are now clickable links to the torrent URL
- Movies tab: poster image widened to 300px (3× previous size); text panel minimum width widened to 440px

### Added — M5: News Feeds + Filter Processor
- CLI Ingester extended to fetch configurable news RSS/Atom feeds after the movie feed; all items stored to `news_items`; `FeedHealth` updated per news feed
- CLI Filter Processor (`src/cli/filter.py`): syncs `filters` table from config; regex-flags matching `news_items` via `matched_filter_id` — never deletes rows; no AI invocation
- FastAPI Web UI: News tab with per-feed-type views (unfiltered / filtered / AI-filtered + raw sub-view)
- `GET /api/news/{feed}/export` and `POST /api/news/{feed}/import` endpoints for AI-filtered feeds (ADR-009)
- Export/Import UI controls (download button + file-upload) on AI-filtered feed views
- Read/unread tracking for `news_items` and `ai_filtered_views`; `keep_as_context` toggle for AI-filtered view rows
- Feed health alerting extended to all news feeds
- New DB tables: `news_items`, `filters`, `ai_filtered_views` (with `source_item_id` FK, denormalised `title`/`url`/`published_at`, `category` as plain text)
- `config.yaml`: `news_feeds` block with `type` and per-feed `filters` (no AI-specific config required)
- New dependency: `feedparser`
- Cron updated: `python src/cli/main.py && python src/cli/filter.py`

### Added — Enrichment
- `movies.imdb_id` column (VARCHAR 20, nullable): populated from OMDb `imdbID` field on enrichment; enables direct IMDb deep-links
- `migrate_001_schema.sh`: idempotent migration script covering all `ai_filtered_views` schema changes and `movies.imdb_id` addition

---

## v0.1.0 — M1–M4 (Movie Pipeline MVP)

### Added
- CLI ingester (`src/cli/main.py`): RSS fetching, parsing, deduplication, feed health tracking
- FastAPI web app (`src/webui/main.py`): JSON API + React frontend (CDN, no build step)
- Shared data layer (`src/common/`): SQLAlchemy models, DB setup, config loading
- On-demand rating enrichment via web UI (OMDb free tier)
- Read-tracking: mark/unmark movies as read, persisted to database
- Feed health alerting via local SMTP (triggers after 24h downtime)
- Configurable genre-specific filtering thresholds (`config.yaml`)
- Genre-priority ordering and year-section grouping in movie list
- MySQL primary + SQLite fallback database support

### Changed
- Project structure: `src/cli/` + `src/webui/` + `src/common/` (ADR-005; supersedes original `pelis/` package proposal)
- Invocation: two separate `python main.py` scripts instead of unified `pelis` CLI

### Security
- Web app binds to 127.0.0.1 only (not network-exposed)
- React JSX escaping prevents XSS from RSS feed data
- Config file stores secrets (file permissions: owner-only read, .gitignore'd)
