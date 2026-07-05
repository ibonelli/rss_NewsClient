# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands must be run from the project root. There is no build step, no test suite, and no package installation configured yet — the project runs directly via Python.

**Setup:**
```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml  # then edit to add OMDb API key and database URL
```

**Run the ingester (one-shot):**
```bash
python src/cli/main.py
```

**Run the web UI:**
```bash
python src/webui/main.py
```

**Cron setup (typical):**
```
0 */2 * * * /path/to/python /path/to/src/cli/main.py
```

## Architecture

This is a two-process Python application called **pelis-feed** for tracking movies from an RSS feed (YTS).

### Two separate processes sharing one database

**CLI Ingester** (`src/cli/`) — runs as a cron job, exits after each run:
1. Fetches the RSS feed (`fetcher.py`) — parses YTS-format titles using regex, extracts poster/genres/ratings from description HTML
2. Deduplicates and stores movies (`dedup.py`) — matches by `torrent_url` first, then `title+year`; merges quality variants rather than creating duplicates
3. Updates feed health and optionally sends SMTP alert if the feed has been down for 24h+ (`alerter.py`)

**Web UI** (`src/webui/`) — FastAPI app, long-running:
- Serves a React frontend (CDN-loaded, no build step) from `src/webui/static/`
- JSON API at `/api/movies`, `/api/movies/{id}/read`, `/api/movies/{id}/unread`, `/api/movies/{id}/enrich`, `/api/health`
- On-demand enrichment calls OMDb API to fetch IMDb and Rotten Tomatoes ratings (`enrichment.py`)
- Filtering and grouping logic (`filters.py`) runs at read time against config-driven thresholds
- Each feed type has its own bookmarkable page route — `/movies`, `/series`, `/news`, `/news/{feed_name}`, `/design`, `/design/{feed_name}` — all served by `routes.py:serve_spa_route` (same `index.html` shell). The active tab/feed is derived client-side from `window.location.pathname` (`parseLocation()` in `app.js`) and kept in sync with the URL bar via the History API (`navigate()`/`replaceLocation()`), so no server-side templating or per-route data is involved

### Shared layer (`src/common/`)
- `models.py` — SQLAlchemy 2.0 ORM: `Movie` and `FeedHealth` tables
- `db.py` — engine/session factory creation and `init_db` (called by both processes at startup; tables are created idempotently)
- `config.py` — loads `config.yaml`, falls back to `config.yaml.example` if absent

### Configuration (`config.yaml`)
All runtime behavior is config-driven:
- `database.url` — SQLAlchemy URL; supports SQLite (`sqlite:///./file.db`) or MySQL (`mysql+pymysql://...`)
- `feed.url` — RSS feed URL
- `filtering` — per-genre and older-movie rating thresholds applied at query time
- `genre_priority` — ordered list controlling sort order within year sections in the UI
- `enrichment.api_key` — required for OMDb enrichment; without it, enrichment is a no-op
- `alerting` — SMTP settings for feed-downtime emails

### Frontend
React loaded via CDN (no npm, no build). `src/webui/static/app.js` uses Babel Standalone for JSX transformation in the browser. FastAPI serves the `index.html` shell at `/` and static assets at `/static/*`.

### Key design decisions
- `genres` and `qualities` columns on `Movie` are stored as JSON-serialized text strings — always parse with `json.loads()` before use
- Movies with no ratings (all null) always pass the filter — they haven't been enriched yet
- The web app injects `config` and `session_factory` into `app.state` and retrieves them via FastAPI `Request` dependencies (`_get_config`, `_get_session` in `routes.py`)
- Both processes call `init_db()` on startup — safe to run concurrently since `create_all` is idempotent
