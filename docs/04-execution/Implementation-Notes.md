# Implementation Notes — pelis-feed

## Scope implemented
- Full MVP: CLI ingester, on-demand enrichment, FastAPI web app with React UI, feed health alerting
- Covers all milestones: M1 (Ingestion), M2 (Enrichment), M3 (Web Application), M4 (Alerting + Polish)

## Files touched

### src/common/ (shared components)
- `src/common/models.py` — SQLAlchemy models (Movie, FeedHealth)
- `src/common/db.py` — Database engine/session setup (MySQL + SQLite)
- `src/common/config.py` — YAML config loading and validation

### src/cli/ (ingester process)
- `src/cli/main.py` — Entry point: RSS fetch, parse, deduplicate, store, health check, alert
- `src/cli/fetcher.py` — RSS feed fetching and parsing
- `src/cli/dedup.py` — Deduplication logic (torrent_url + title/year merge)
- `src/cli/alerter.py` — Feed health tracking + SMTP alert

### src/webui/ (FastAPI web app)
- `src/webui/main.py` — Entry point: FastAPI app startup (Uvicorn)
- `src/webui/app.py` — FastAPI app factory + static file mounting
- `src/webui/routes.py` — JSON API route handlers
- `src/webui/filters.py` — Filtering and sorting logic (config-driven)
- `src/webui/enrichment.py` — On-demand enrichment endpoint logic
- `src/webui/static/index.html` — React shell (CDN-loaded)
- `src/webui/static/app.js` — React components (JSX via Babel CDN)
- `src/webui/static/styles.css` — Application styles

### Root
- `config.yaml` — User configuration (filtering rules, DB URL, SMTP, etc.)
- `requirements.txt` — Python dependencies

## Key decisions (links to ADRs)
- ADR-001: FastAPI as web framework (rendering approach superseded by ADR-004)
- ADR-002: SQLAlchemy with MySQL primary / SQLite fallback
- ADR-003: On-demand enrichment (user-triggered, not at ingestion time)
- ADR-004: React via CDN replaces Jinja2/HTMX — no build step

### Structural deviation from Architecture Overview
- Original proposed structure: `pelis/` package with `pelis ingest`/`pelis serve` CLI commands (Click-based)
- Actual structure: `src/cli/main.py` and `src/webui/main.py` as two independent scripts
- Rationale: Clearer separation of concerns; the ingester is generic (could work with non-movie feeds); no need for a unified CLI package

## Edge cases handled
- RSS feed format changes: parser logs warnings for unparseable entries, does not crash
- Enrichment API timeout: returns error to user, does not block other operations
- SQLite concurrent access: acceptable since ingester runs briefly every ~2h
- Deduplication: handles both URL-exact matches and title+year fuzzy matches (merges qualities)
- Empty/malformed config: validation on load with clear error messages

## Known limitations
- No bulk enrichment — user must click per-movie "refresh ratings"
- In-browser JSX transform via Babel CDN adds ~1s to initial page load
- CDN-loaded React requires internet on first visit (cached after)
- No Alembic migrations — schema changes require manual ALTER TABLE or DB recreate
- No authentication (localhost-only, single user)

## Migration steps (if needed)
- First run: `python src/cli/main.py` or `python src/webui/main.py` will create tables automatically via SQLAlchemy `create_all()`
- No manual migrations for initial deployment

## How to test locally
1. Install dependencies: `pip install -r requirements.txt`
2. Copy/edit `config.yaml` with your database URL and preferences
3. Run ingestion: `python src/cli/main.py` — fetches RSS, stores movies
4. Run web app: `python src/webui/main.py` — starts FastAPI on configured host:port
5. Open browser to `http://127.0.0.1:8080` — verify movie list renders
6. Click a movie's "mark as read" — verify it disappears on refresh
7. Click "refresh ratings" on a movie — verify enrichment returns data (or graceful error)
8. Stop the feed source or wait 24h+ without ingesting — verify email alert fires
