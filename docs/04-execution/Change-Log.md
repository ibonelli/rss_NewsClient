# Change Log — pelis-feed

## Unreleased — M5 (News Feeds + Filter Processor)

### Planned
- CLI Ingester: extend to fetch news RSS/Atom feeds; store all items to `news_items`; update `feed_health` per news feed
- CLI Filter Processor (`src/cli/filter.py`): new process; sync `filters` table from config; regex pass on filtered feeds; Claude CLI AI pass on AI-filtered feeds; upsert `ai_filtered_views` and `categories`
- FastAPI Web UI: News tab with per-feed-type views (unfiltered / filtered / AI-filtered + raw sub-view)
- Read/unread tracking for `news_items` and `ai_filtered_views`; `keep_as_context` toggle for AI-filtered view rows
- Feed health alerting extended to all news feeds
- New DB tables: `news_items`, `filters`, `categories`, `ai_filtered_views`; `feed_health` updated to multi-row (one per feed)
- `config.yaml`: `news_feeds` block with `type`, per-feed `filters`, `claude_prompt`, `claude_timeout_seconds`
- New dependency: `feedparser`
- Cron updated: `python src/cli/main.py && python src/cli/filter.py`

---

## v0.1.0 — M1–M4 (Movie Pipeline MVP)

### Added
- CLI ingester (`src/cli/main.py`): RSS fetching, parsing, deduplication, feed health tracking
- FastAPI web app (`src/webui/main.py`): JSON API + React frontend (CDN, no build step)
- Shared data layer (`src/common/`): SQLAlchemy models, DB setup, config loading
- On-demand rating enrichment via web UI (OMDb/TMDb free tier)
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
