# Implementation Notes — pelis-feed

## Scope implemented

All milestones M1–M5 are implemented and running in production.

- **M1 — Ingestion:** CLI ingester, RSS fetch/parse, dedup, storage
- **M2 — Enrichment:** On-demand OMDb enrichment via web UI; stores `imdb_id` for direct linking
- **M3 — Web Application:** FastAPI + React CDN frontend; movie list with Filtered/All toggle; rating badges link to IMDb/RT
- **M4 — Alerting + Polish:** Feed health tracking per feed; SMTP alert on 24h downtime
- **M5 — News Feeds + Filter Processor:** News ingestion (all types); CLI Filter Processor (regex only); News tab in web UI; export/import for AI-filtered feeds

## Files touched

### src/common/ (shared components)
- `src/common/models.py` — SQLAlchemy models: `Movie`, `FeedHealth`, `NewsItem`, `Filter`, `AIFilteredView`
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
