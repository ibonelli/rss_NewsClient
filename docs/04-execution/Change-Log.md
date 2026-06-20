# Change Log — pelis-feed

## Unreleased

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
