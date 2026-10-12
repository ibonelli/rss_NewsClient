# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run from the project root. No build step, no package installation beyond `requirements.txt`. Use the project venv (`.venv/bin/python3`) if present.

**Setup:**
```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml  # then edit: DB url, feed URLs, OMDb key, news/design feeds
```

**Run the ingest + filter pipeline (one-shot, what cron runs):**
```bash
python src/cli/main.py && python src/cli/filter.py
# or:
./run_pipeline.sh   # same two steps, with log rotation; skips filter.py if main.py fails
```

**Run the web UI (long-running):**
```bash
python src/webui/main.py
```
No auto-reload — changes to `routes.py` or `app.js` require a manual restart.

**Tests** (`unittest`, no pytest installed):
```bash
python -m unittest tests/test_fetcher.py
```

**Schema migrations** — `create_all` only adds new tables, so column/index changes to existing tables need a manual, idempotent migration script:
```bash
tools/migrate_00N_<description>.sh   # each checks whether its change is already applied before running
```
Add a new `tools/migrate_0NN_*.sh` (following the existing numbering) for any future schema change that isn't a brand-new table.

**Database backup** (reads `database.url` from config; MySQL via `mysqldump`, SQLite via `sqlite3 .backup`):
```bash
tools/backup_db.sh [OUTPUT_DIR]   # default ./backups (git-ignored); BACKUP_KEEP_DAYS=N prunes older backups
```

**Cron (typical, every 2h):**
```
0 */2 * * * cd /path/to/repo && ./run_pipeline.sh
```

## Architecture

**pelis-feed** (repo name `RSS_NewsClient`) tracks four content types from feeds: movies (YTS), TV series (EZTV), news articles, and design articles.

### Three processes sharing one database (ADR-006)

1. **CLI Ingester** (`src/cli/main.py`) — fetches the movie feed, series feed, and every configured news/design feed; dedupes and stores raw rows; updates `feed_health`; sends an SMTP alert if a feed has been down 24h+ (`alerter.py`). Parsing lives in `fetcher.py` (YTS/EZTV titles and description HTML via regex); storage/merge logic for movies and series lives in `dedup.py`.
2. **CLI Filter Processor** (`src/cli/filter.py`) — runs immediately after the ingester. Syncs `Filter` rows from `news_feeds[].filters` in config, then regex-matches unmatched `NewsItem` rows for feeds of `type: filtered`, setting `matched_filter_id`. Never deletes rows; non-matches just stay hidden from the filtered UI view. Feeds of `type: unfiltered` are untouched by this step.
3. **Web UI** (`src/webui/`) — FastAPI app, long-running. Serves a React frontend (CDN-loaded, Babel Standalone for JSX, no build step) from `src/webui/static/`, plus JSON APIs per content type.

AI-based news filtering is **not** performed inside the app. It was originally done via a direct Claude CLI call from the filter processor (ADR-008), then removed in favor of a fully external workflow (ADR-009): `GET /api/news/{feed_name}/export` dumps unread items as JSON, and an external script/tool (see `run_ai_filtering.sh`, `README_LLM.md`) processes them outside the repo. The `ai_filtered` feed type, `AIFilteredView` model, and `ai_filtered_views` table are legacy — schema is retained but no route or process reads/writes them anymore.

### Content types and their models (`src/common/models.py`)
- **Movie** — dedup by `torrent_url_hash` first, then `title`+`year`; quality variants merge into one row (`qualities` JSON) rather than creating duplicates. On-demand OMDb enrichment (`src/webui/enrichment.py`) fills IMDb/RT ratings; without `enrichment.api_key` configured, enrichment is a no-op.
- **Series** / **SeriesEpisode** — split in two (ADR-012): `Series` is one row per show (category derived from `is_following`/`is_ignored`: Inbox / Following / Ignored), `SeriesEpisode` is one row per season/episode with its own quality variants. `series_feed.follow_filters` in config auto-promotes a newly-ingested series straight to Following (checked once, at first ingest only).
- **NewsItem** — raw item from any news feed. Each `news_feeds` config entry has a `type` (`unfiltered` | `filtered`) and an optional `tag` (groups feeds into UI tabs; defaults to `"General"`; tab order controlled by `news_tag_priority`, ADR-016).
- **DesignItem** — same shape as News (url/summary/image), from separately configured `design_feeds`.
- **SavedEntry** — a common-format snapshot (ADR-017), one table for all four content types, keyed by `(source_type, source_id)` with no FK (a single FK can't reference four parent tables — validated at the application layer only). Populated by a "Save" action available on every content type; flat list + remove only, no read/unread tracking, unlike the other four types.
- `hash_url()` — SHA-256 of a URL/torrent URL, stored alongside the raw value and indexed instead of it. utf8mb4 VARCHAR(1000+) exceeds InnoDB's 3072-byte index-key limit, so long URL columns can't be indexed directly.

### Routing
Each content type has its own bookmarkable route family — `/movies`, `/series`, `/news`, `/news/{tag}`, `/news/{tag}/{feed_name}`, `/design`, `/design/{feed_name}`, `/saved` — all served by `routes.py:serve_spa_route` returning the same `index.html` shell. The active tab/feed is derived client-side from `window.location.pathname` (`parseLocation()` in `app.js`) and kept in sync via the History API (`navigate()`/`replaceLocation()`) — no server-side templating or per-route data. `GET /api/news` returns feeds pre-grouped and pre-sorted by tag priority; the client only groups the already-ordered array. An old-style or unrecognized News path falls back to the News tab's own default rather than redirecting (ADR-016 — deliberate, not backward-compatible).

### Shared layer (`src/common/`)
- `models.py` — SQLAlchemy 2.0 ORM, see content types above.
- `db.py` — engine/session factory creation and `init_db` (called by both CLI processes and the web UI at startup; `create_all` is idempotent, safe to run concurrently — but does **not** alter existing tables, hence `tools/migrate_*.sh`).
- `config.py` — loads `config.yaml`, falls back to `config.yaml.example` if absent.

### Configuration (`config.yaml`)
All runtime behavior is config-driven — `database.url` (SQLite or MySQL via `pymysql`), `feed.url` (movies), `series_feed.url` + `follow_filters`, `news_feeds` (list of `{name, url, type, tag, filters}`), `news_tag_priority`, `design_feeds`, `filtering` (per-genre and older-movie rating thresholds, applied at query time in `src/webui/filters.py`), `genre_priority` (sort order), `enrichment.api_key`, `alerting` (SMTP), `webapp.host`/`port`.

### Docs and ADRs
`docs/adr/ADR-001` through `ADR-017` record the non-obvious architectural decisions and their rejected alternatives (three-process split, why AI filtering is external, the Saved Entries schema, the News tag/routing scheme, etc.) — check there before revisiting a structural decision, since the tradeoffs are usually already documented. `docs/` also holds a fuller SDLC-style doc set (scoping, requirements, planning, architecture, execution, documentation) kept alongside ADRs.

### Key design decisions
- `genres` and `qualities` columns are JSON-serialized text — always parse with `json.loads()` before use.
- Items with no ratings (all null) always pass the movie filter — they haven't been enriched yet.
- The web app injects `config` and `session_factory` into `app.state`, retrieved via FastAPI `Request` dependencies (`_get_config`, `_get_session` in `routes.py`).
- `full_content` (NewsItem) uses `Text().with_variant(LONGTEXT(), "mysql")` — plain MySQL `TEXT` caps at ~65KB and some feeds' raw HTML exceeds that.
