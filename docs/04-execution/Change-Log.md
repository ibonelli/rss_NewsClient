# Change Log — pelis-feed

## Unreleased

### Added — M8: Movies Two-Toggle View
- `GET /api/movies?read=false&flagged=true` — replaces old `?filtered=bool` and the M8-interim `?view=...`
  - `read` (bool, default `false`): `false` = unread movies, `true` = read movies
  - `flagged` (bool, default `true`): `true` = passes rating/genre filter ("Flagged"), `false` = fails filter ("Un-Flagged")
- `POST /api/movies/read-all?flagged=true|false` — scopes mark-all to the currently visible Flagged or Un-Flagged set only
- No schema change — Flagged/Un-Flagged split computed at runtime from config thresholds (no `is_flagged` column)
- Unenriched movies (null ratings) appear in Flagged results (pass-by-default behaviour preserved)
- Movies tab: two independent toggle buttons — **Unread/Read** and **Flagged/Un-Flagged**; default Unread + Flagged
- "Mark All Read" visible only when Unread toggle is active; scoped to the current Flagged/Un-Flagged state

### Added — M7: Series Two-Table Split + Ignore
- `series` table: one row per unique title (`title` UNIQUE, `imdb_id` nullable, `is_ignored` bool)
- `series_episodes` table: one row per `(series_id, season, episode)`; FK → `series.id`; carries `qualities`, `feed_entry_date`, `ingested_at`, `is_read`
- Deduplication now two-level: upsert series title first, then upsert episode; `session.flush()` used between levels to populate `series.id` before the episode insert
- `is_ignored` at title level only — new episodes for an ignored series automatically inherit ignore status via JOIN at query time (no per-episode flag)
- `GET /api/series?view=unread|all|ignored` — three views (replaces old `filtered|all|read`)
  - `unread` (default): non-ignored series with at least one unread episode
  - `all`: non-ignored series, all episodes regardless of read status
  - `ignored`: only ignored series
- Response includes `series.id`, `imdb_url` (always present; IMDb title-search URL when `imdb_id` is null per ADR-010)
- `POST /api/series/{series_id}/ignore` and `/api/series/{series_id}/unignore` — PK-based (O(1) single row update)
- `POST /api/series/episodes/{episode_id}/read` and `/unread` — episode-level read tracking
- `POST /api/series/read-all` now marks `series_episodes.is_read`
- Series tab: view switcher (Unread / All / Ignored); Ignore/Unignore per title; Mark All Read hidden on Ignored view
- `clear_db.sh`: auto-detects old `series` schema (M6) and drops/recreates it; skips missing tables gracefully; calls `init_db` after clearing

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
