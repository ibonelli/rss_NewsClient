# Implementation Notes — pelis-feed

## Scope implemented
- Full MVP: CLI ingester, on-demand enrichment, FastAPI web app with React UI, feed health alerting
- Covers all milestones: M1 (Ingestion), M2 (Enrichment), M3 (Web Application), M4 (Alerting + Polish)
- **M5 (News Feeds + Filter Processor): not yet implemented — see Pending section below**

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
- ADR-005: `src/cli/` + `src/webui/` + `src/common/` structure instead of unified `pelis/` package
- ADR-006: Three-process architecture — CLI Ingester + CLI Filter Processor + FastAPI Web UI *(Filter Processor pending M5)*
- ADR-007: Two-table design for AI-filtered news (`news_items` + `ai_filtered_views`) *(pending M5)*
- ADR-008: Claude CLI for AI-filtered news processing *(pending M5)*

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

## Migration steps (M1–M4)
- First run: `python src/cli/main.py` or `python src/webui/main.py` creates tables automatically via SQLAlchemy `create_all()`
- No manual migrations for initial deployment

## How to test locally (M1–M4)
1. Install dependencies: `pip install -r requirements.txt`
2. Copy/edit `config.yaml` with your database URL and preferences
3. Run ingestion: `python src/cli/main.py` — fetches RSS, stores movies
4. Run web app: `python src/webui/main.py` — starts FastAPI on configured host:port
5. Open browser to `http://127.0.0.1:8080` — verify movie list renders
6. Click a movie's "mark as read" — verify it disappears on refresh
7. Click "refresh ratings" on a movie — verify enrichment returns data (or graceful error)
8. Stop the feed source or wait 24h+ without ingesting — verify email alert fires

---

## Pending — M5 (News Feeds + Filter Processor)

### Scope to implement
Covers Epics 5 and 6 from the Delivery Plan: news feed ingestion, regex + AI filtering, and the News tab in the web UI.

### Files to create

**src/cli/**
- `src/cli/filter.py` — Filter Processor entry point: sync `filters` table from config, run regex pass, run AI pass per AI-filtered feed, upsert `ai_filtered_views` and `categories`

**src/common/**
- `src/common/models.py` — extend with: `NewsItem`, `Filter`, `Category`, `AIFilteredView` models; update `FeedHealth` to multi-row (add `feed_name` column, remove single-row assumption)

**src/webui/**
- `src/webui/routes.py` — extend with all news API routes: `/api/news`, `/api/news/{feed_name}/items`, `/api/news/{feed_name}/raw`, read/unread/keep/unkeep endpoints
- `src/webui/static/app.js` — extend React UI with News tab, feed type sub-views (unfiltered / filtered / AI-filtered / raw)

**src/cli/ (extend existing)**
- `src/cli/fetcher.py` — extend to fetch news RSS/Atom feeds in addition to the movie feed; use `feedparser` for Atom support
- `src/cli/alerter.py` — extend feed health check and SMTP alerting to cover all news feeds (currently movie feed only)
- `src/cli/main.py` — call news fetching after movie ingestion; update `FeedHealth` per news feed

**Root**
- `config.yaml` / `config.yaml.example` — add `news_feeds` block (name, url, type, filters, claude_prompt, claude_timeout_seconds)
- `requirements.txt` — add `feedparser`

### Key constraints to enforce
- **C-007:** All feed definitions and filter patterns MUST come from `config.yaml`, never hardcoded
- **C-008:** AI-filtered feeds MUST invoke `claude --print` subprocess; no other AI service
- **NFR-005:** Each AI-filtered feed invocation MUST respect `claude_timeout_seconds`; log and skip on timeout
- **NFR-006:** Log item count sent to and received from Claude per feed per run
- **F-004:** No paid third-party news enrichment APIs

### Migration steps (M5)
The following new tables are added by `create_all()` — no manual SQL needed on a fresh DB. On an existing DB with only `movies` and `feed_health`:
1. `create_all()` will add `news_items`, `filters`, `categories`, `ai_filtered_views`
2. `feed_health` requires adding a `feed_name` column (unique) and migrating the existing single row — manual `ALTER TABLE` or DB recreate required

### Edge cases to handle
- **News feed deduplication:** skip `news_items` rows with a duplicate `(url, feed_name)` — idempotent re-ingestion
- **Filtered feed with no matches:** valid state — `matched_filter_id` remains null for all items; nothing appears in News tab filtered view (correct behaviour)
- **Claude CLI not installed:** check subprocess availability at Filter Processor startup; log clearly, skip AI-filtered feeds for the cycle, do not crash
- **Claude returns ID not in input batch:** discard silently (V-016); log warning
- **Claude returns invalid JSON:** catch `json.JSONDecodeError`; log raw output excerpt; skip AI pass for that feed
- **`keep_as_context` rows:** never overwrite `is_read` or `keep_as_context` when upserting existing `ai_filtered_views` rows (V-020)
- **Atom vs RSS 2.0:** use `feedparser` to normalise both formats; log and skip unparseable items
- **Empty news feed:** zero items fetched is valid — update `feed_health` as success, log item count

### How to test locally (M5 — once implemented)
1. Add at least one news feed of each type to `config.yaml`
2. Run ingester: `python src/cli/main.py` — verify `news_items` rows appear in DB
3. Run filter processor: `python src/cli/filter.py`
   - Filtered feed: verify `matched_filter_id` is set on matching items
   - AI-filtered feed: verify `ai_filtered_views` rows appear with category/summary/tags
4. Run web app and open News tab — verify each feed type renders correctly
5. Mark a news item as read — verify it persists after page refresh
6. For an AI-filtered feed: verify raw sub-view shows all `news_items` for that feed
7. Set `keep_as_context = true` on an AI-filtered view item; re-run filter processor — verify that item appears in the context section sent to Claude (check logs)
