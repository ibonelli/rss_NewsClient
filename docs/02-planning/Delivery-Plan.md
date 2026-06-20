# Delivery Plan — pelis-feed

## 1) Scope recap

### In scope
- RSS feed ingestion from `https://yts.ag/rss` (cron-triggered CLI)
- News RSS/Atom feed ingestion — unfiltered, filtered, and AI-filtered types
- Scheduled polling (~2 hours via system cron) for all feeds
- SQLite/MySQL database for persistent storage (dual-backend)
- Rating enrichment from free sources (IMDb, RT expert, RT audience)
- CLI Filter Processor — regex-matches `news_items` for `filtered` feeds; flags matches via `matched_filter_id`; never deletes rows
- FastAPI web application for filtered movie browsing, series browsing, and news reading
- Configurable genre-specific filtering rules (config file)
- Config-driven news feed and filter definitions synced to `filters` table
- Read-tracking via web UI (persisted in DB) for movies, series, and news
- Email alerting (local SMTP) when any feed is down >24h
- EZTV RSS ingestion for TV series with S##E## parsing and quality variant grouping
- Series tab in the web UI (title → season → episode, IMDb link per series, torrent page link per quality variant)

### Out of scope
- Downloading or streaming movies or series
- Multi-user support / authentication
- Mobile notifications
- Deployment to cloud/remote servers (local only)
- Paid API integrations
- Hosting or invoking any AI classification tool
- Rating enrichment for series (OMDb lacks reliable episode-level data)
- AI-assisted filtering for series

## 2) Milestones

| Milestone | Deliverable | Owner |
|---|---|---|
| M1 — Ingestion | CLI Ingester fetches movie RSS, parses entries, stores in DB. Deduplication works. | Self |
| M2 — Enrichment | Movies are enriched with IMDb + RT ratings from free sources. Failures handled gracefully. | Self |
| M3 — Web Application (Movies) | FastAPI app serves filtered, grouped movie view. Read-tracking works. | Self |
| M4 — Alerting + Polish | Email alerts on feed downtime >24h. Config-driven filtering is tunable. | Self |
| M5 — News Feeds | CLI Ingester fetches news feeds. CLI Filter Processor flags matching items via regex. News tab in web UI with read tracking, AI-filtered sub-views, and export/import workflow for AI-filtered feeds. | Self |
| M6 — Series Feed | CLI Ingester fetches EZTV RSS, parses and deduplicates series entries. Series tab in web UI shows episodes grouped by title → season, with IMDb and torrent page links per quality variant. Read-tracking and alerting work. | Self |

## 3) Work Breakdown (Epics → Stories)

### Epic 1: Ingestion (M1)
- **Story 1.1:** Set up three-process project structure, dependencies, and config loading (FR-016, C-001, C-003, C-007)
- **Story 1.2:** Implement movie RSS feed fetcher with error handling (FR-001, NFR-001)
- **Story 1.3:** Implement database layer with SQLite backend (FR-002, C-002)
- **Story 1.4:** Add MySQL backend support behind same interface (FR-002, C-002)
- **Story 1.5:** Implement deduplication logic — same name/URL merges qualities (FR-003)
- **Story 1.6:** Track feed health — record last successful fetch timestamp per feed (FR-008)

### Epic 2: Enrichment (M2)
- **Story 2.1:** Research and select free rating source(s) — OMDb free tier, TMDb, imdbapi.dev (Q-001)
- **Story 2.2:** Implement IMDb rating enrichment (FR-009)
- **Story 2.3:** Implement RT expert + audience rating enrichment (FR-010, FR-011)
- **Story 2.4:** Graceful failure handling — skip enrichment on errors, retry later (FR-012)

### Epic 3: Web Application — Movies (M3)
- **Story 3.1:** FastAPI app skeleton with Movies tab (C-003, C-006)
- **Story 3.2:** Implement filtering logic — genre-specific rating thresholds from config (FR-005, FR-016)
- **Story 3.3:** Implement grouping — same-name movies show together (FR-006)
- **Story 3.4:** Implement year sections (2026→2021) with older movies in summary section (FR-013, FR-014)
- **Story 3.5:** Implement genre-priority ordering within year sections (FR-015)
- **Story 3.6:** Implement read-tracking toggle in UI, persisted to DB (FR-017, FR-018)

### Epic 4: Alerting & Polish (M4)
- **Story 4.1:** Implement feed downtime detection (>24h since last success) (FR-007)
- **Story 4.2:** Send email alert via local SMTP (FR-007, C-005)
- **Story 4.3:** Verify end-to-end flow: ingest → enrich → serve → track

### Epic 5: News Feed Ingestion (M5)
- **Story 5.1:** Extend config schema for news feed definitions with `type` field; sync `filters` table at filter processor startup (FR-019, C-007)
- **Story 5.2:** CLI Ingester — fetch news RSS/Atom feeds, store all items to `news_items` (FR-020, FR-021, FR-026)
- **Story 5.3:** CLI Filter Processor — regex pass: match items against `filters` table, write `matched_filter_id` FK (FR-022)
- ~~**Story 5.4:** Removed — Claude CLI AI pass replaced by export/import (see ADR-009).~~
- **Story 5.4a:** Web UI — `GET /api/news/{feed}/export` endpoint: returns unread `news_items` + `keep_as_context` `ai_filtered_views` as a JSON download (FR-033, NFR-006)
- **Story 5.4b:** Web UI — `POST /api/news/{feed}/import` endpoint: replace `ai_filtered_views` for the feed with imported rows; persist `source_item_id` FK (FR-034)
- **Story 5.4c:** News tab UI — Export download button and file-upload import control for `ai_filtered` feeds (FR-035, FR-036)
- **Story 5.5:** Extend feed health tracking and email alerting to all news feeds (FR-025, FR-007)

### Epic 6: News Web UI (M5)
- **Story 6.1:** Add News tab to FastAPI web app (FR-028)
- **Story 6.2:** Implement read/unread tracking for news items and AI-filtered views (FR-029)
- **Story 6.3:** Filtered feed view — show only items with non-null `matched_filter_id`, display filter name (FR-030)
- **Story 6.4:** AI-filtered feed view — from `ai_filtered_views` with category, summary, tags (FR-031)
- **Story 6.5:** Raw unprocessed sub-view for AI-filtered feeds — all `news_items` for that feed (FR-032)

### Epic 7: Series Ingestion (M6)
- **Story 7.1:** Add `Series` table to DB model (FR-042)
- **Story 7.2:** Implement EZTV RSS fetcher with error handling (FR-039, NFR-001)
- **Story 7.3:** Implement series title parser — regex for series name, S##E##, quality; extract IMDb ID and torrent page URL from feed fields (FR-040)
- **Story 7.4:** Implement deduplication — merge quality variants by `title+season+episode` (FR-041)
- **Story 7.5:** Extend feed health tracking and alerter to EZTV feed (FR-043, FR-047)

### Epic 8: Series Web UI (M6)
- **Story 8.1:** Add Series tab to FastAPI web app (FR-044)
- **Story 8.2:** Implement grouping — series title → season → episode, with IMDb link per title and torrent page link per quality variant (FR-045)
- **Story 8.3:** Implement read-tracking for series entries (FR-046)

## 4) Dependencies
- **External teams:** None (solo project)
- **Vendors:** Free-tier API access (OMDb/TMDb/imdbapi.dev)
- **Environments:** Local machine with Python, system cron, local SMTP server
- **Approvals:** None

## 5) Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Dual DB complexity (SQLite + MySQL) | Higher testing burden, potential ORM differences | Use SQLAlchemy as abstraction layer; test both backends |
| Filter tuning difficulty | Genre-specific thresholds hard to calibrate initially | Make thresholds easily adjustable via config; iterate after first data |
| Free rating APIs may be unreliable | Missing or stale ratings | Support multiple sources; graceful fallback; enrich asynchronously |
| YTS RSS feed format changes | Ingestion breaks silently | Validate parsed fields; alert on parse failures |
| Import JSON schema mismatch | Import silently drops fields or fails | Validate import payload against expected schema before persisting; return clear error on failure |
| User forgets to re-import after new items arrive | AI-filtered view goes stale | UI could show count of unread items pending export as a visual cue |
| News RSS format variability (Atom vs RSS 2.0) | Parser fails on some feeds | Use `feedparser` library; log unparseable items and skip |
| EZTV title format inconsistency | Parser misses entries without standard S##E## pattern | Log and skip unparseable entries; revisit regex after live feed inspection (Q-009, Q-010) |
| IMDb ID absent from some EZTV RSS entries | Series IMDb link missing for those entries | Store IMDb ID as nullable; omit link in UI when absent (Q-011) |
| EZTV feed reliability | Series ingestion breaks silently | Existing feed health + alerter pattern covers this (FR-043, FR-047) |

## 6) Rollout strategy
- **Direct local deploy** — no staged rollout needed for personal project
- **Cron setup:** Add cron job running ingester then filter processor sequentially after M1/M5 are verified
- **Web app:** Run locally on-demand after M3
- **Rollback:** Git-based — revert to previous commit if needed

## 7) Definition of Done (DoD)
- [ ] Code runs without errors for the milestone's scope
- [ ] Basic tests cover happy path
- [ ] HTML view renders correctly (M3+)
- [ ] Config file is documented with example values
