# Requirements — pelis-feed

## 1) Goal
- The system shall automatically ingest movie data from the YTS RSS feed and news from configurable RSS/Atom news feeds, provide on-demand rating enrichment for movies and AI-assisted filtering/classification for news, and serve a filterable, read-tracked web-based view grouped appropriately for each content type.

## 2) Personas / Users
- Persona A: Self (sole user) — wants to discover quality movies and relevant news without manual browsing

## 3) Functional Requirements

### Ingestion — Movies
- **FR-001:** The system MUST fetch RSS data from `https://yts.ag/rss` every ~2 hours via a scheduled process.
- **FR-002:** The system MUST store ingested movie data in a SQLite or MySQL database.
- **FR-003:** The system MUST handle duplicate entries (same name or same torrent URL) by appending new information (e.g., different quality/resolution) to the existing movie record rather than creating a new entry.
- **FR-008:** The system MUST track feed health by recording the timestamp of the last successful fetch for each configured feed (movie and news).

### Ingestion — News
- **FR-019:** The system MUST support ingesting from news RSS/Atom feeds configurable in `config.yaml`, each with a `type` field: `unfiltered`, `filtered`, or `ai_filtered`.
- **FR-020:** News feeds MUST be fetched on the same ~2h cron cycle as the movie feed.
- **FR-021:** Unfiltered news feeds MUST store all fetched items without filtering.
- **FR-022:** Filtered news feeds MUST store ALL fetched items. Items matching the configured regex MUST have the matching filter identifier recorded in a dedicated `matched_filter` field; non-matching items have this field null.
- **FR-023:** AI-filtered news feeds MUST store all fetched items in the raw `news_items` table AND invoke the Claude CLI with those items as JSON. Claude CLI output MUST be persisted in a separate `ai_filtered_views` table.
- **FR-024:** The Claude CLI prompt/instructions for AI-filtered feeds MUST be configurable per feed in `config.yaml`.
- **FR-025:** Feed health tracking MUST extend to all news feeds, recording last successful fetch per feed.

### Enrichment — Movies
- **FR-009:** The system MUST extract any ratings provided natively by the RSS feed during ingestion (if available).
- **FR-010:** The web application MUST provide a per-movie "refresh ratings" button that triggers on-demand enrichment from a free external source (OMDb, imdbapi.dev, TMDb, or scraping).
- **FR-011:** On-demand enrichment MUST fetch IMDb rating, Rotten Tomatoes expert rating, and RT audience rating when triggered.
- **FR-012:** The system SHOULD gracefully handle enrichment failures (source unavailable) and display an error state to the user without crashing.

### News Data Model
- **FR-026:** Each stored `news_items` row MUST carry: title, URL, publication date, source feed name, full content, ingestion timestamp, read status, and `matched_filter` (nullable; populated only for filtered feeds when a regex match occurs).
- **FR-027:** The `ai_filtered_views` table MUST contain: source feed name, title, URL, publication date, category (AI-assigned), summary (AI-generated), tags (AI-generated list), read status, and ingestion timestamp.

### Web Application — Movies
- **FR-004:** The system MUST provide a local web application (FastAPI) that serves the filtered movie view dynamically from the database.
- **FR-005:** The web application MUST filter movies using configurable rules based on genre and ratings (IMDb, RT expert, RT public), where rating thresholds vary by genre.
- **FR-006:** The web application MUST group movies with the same name (or same torrent URL), showing available qualities/resolutions together.
- **FR-013:** The view MUST be organized by year, from 2026 down to 2021 (6 years from today), with a separate section per year.
- **FR-014:** Movies older than the 6-year window MUST appear in a summarized section with stricter rating filtering.
- **FR-015:** Within each year section, movies MUST be ordered by genre priority: Action and Romantic Comedies first, Documentaries last, other genres in between.
- **FR-016:** Filtering configuration MUST be stored in a config file (not hardcoded), adjustable without restarting the web application.

### Web Application — News
- **FR-028:** The web application MUST provide a separate "News" tab, distinct from the Movies tab.
- **FR-029:** The news view MUST provide per-item read/unread tracking with behavior identical to movies (persisted in DB, survives restart).
- **FR-030:** For filtered feeds, the News tab MUST show only items where `matched_filter` is not null, displaying the matched filter name/pattern alongside each item.
- **FR-031:** For AI-filtered feeds, the News tab MUST display items from the `ai_filtered_views` table, showing category, summary, and tags. Read/unread tracking for AI-filtered feeds MUST be applied to `ai_filtered_views` rows.
- **FR-032:** For AI-filtered feeds, the News tab MUST also provide a sub-view displaying the full raw `news_items` for that feed, allowing the user to browse unprocessed items alongside the AI-filtered view.

### Read Tracking
- **FR-017:** The web application MUST provide a UI mechanism (button/toggle) to mark movies as "already read/seen" so they are excluded from the view.
- **FR-018:** Read-tracking status MUST be persisted in the database and survive application restarts.

### Alerting
- **FR-007:** The system MUST send an email alert via local SMTP if any configured feed (movie or news) is unreachable for more than 24 hours.

## 4) Non-Functional Requirements (NFRs)
- **NFR-001 (Availability):** The scheduler MUST tolerate transient feed failures without crashing — retry on next cycle.
- **NFR-002 (Performance):** Report generation SHOULD complete within 30 seconds for up to 10,000 stored movies.
- **NFR-003 (Maintainability):** Code MUST be written in Python with clear separation between ingestion, enrichment, and report generation.
- **NFR-004 (Cost):** The system MUST NOT use paid APIs for movie rating enrichment.
- **NFR-005 (AI Timeout):** The Claude CLI call for AI-filtered feeds MUST have a configurable timeout; the ingester MUST NOT block indefinitely and MUST log a failure if the timeout is exceeded.
- **NFR-006 (AI Observability):** The ingester SHOULD log the number of items sent to and received from Claude CLI per run per feed.

## 5) Data Requirements
- **Movies:** title, year, genre(s), torrent URL, quality/resolution, IMDb rating, RT expert rating, RT audience rating, poster URL, feed entry date, enrichment date, read status
- **News — `news_items` (all feed types):** title, URL, publication date, source feed name, full content, ingestion timestamp, read status, matched_filter (nullable)
- **News — `ai_filtered_views` (AI-filtered feeds only):** source feed name, title, URL, publication date, category, summary, tags (list), read status, ingestion timestamp
- Retention: indefinite (database on disk)
- PII classification: None

## 6) Integration Requirements
- Upstream: YTS RSS feed (`https://yts.ag/rss`), configurable news RSS/Atom feeds, TMDb/OMDb/imdbapi.dev or scraping for movie ratings, Claude CLI for AI-filtered news processing
- Downstream: Local SMTP for email alerts
- Contracts: RSS XML format (subject to change without notice); Claude CLI JSON input/output schema (TBD — see Q-005)

## 7) Acceptance Criteria
- **AC-001:** Running the scheduler for 24h produces at least one successful fetch and stores data in the database.
- **AC-002:** Report HTML contains movies grouped by name, sectioned by year, ordered by genre priority.
- **AC-003:** Changing filter config and regenerating report produces different output.
- **AC-004:** Marking a movie as read and regenerating excludes it from the report.
- **AC-005:** Simulating feed downtime >24h triggers an email alert.
- **AC-006:** Movies have enriched ratings from at least one external source.
- **AC-007:** Unfiltered news feeds store all fetched items; read/unread status survives app restart.
- **AC-008:** Filtered news feeds store all items; only items with a non-null `matched_filter` appear in the News tab, with the filter name displayed.
- **AC-009:** AI-filtered news feeds invoke Claude CLI, and returned categories/summaries/tags appear in `ai_filtered_views`.
- **AC-010:** The web UI News tab is accessible and displays news items independently of the Movies tab.
- **AC-011:** For AI-filtered feeds, both the AI-filtered sub-view and the raw unprocessed sub-view are accessible in the News tab.

## 8) Open Questions
- **Q-001:** Which free rating source is most reliable/complete for movies? (TMDb, OMDb free tier, imdbapi.dev, scraping?)
- ~~**Q-002:** Resolved — see ADR-001 (FastAPI web app)~~
- **Q-003:** What are the initial genre-specific rating thresholds? (can iterate via config)
- **Q-004:** What genre ordering should be used between "Action/RomCom" (first) and "Documentary" (last)?
- **Q-005:** What is the expected JSON schema for Claude CLI input/output for AI-filtered feeds? (needs definition before implementation)
- **Q-006:** Should AI-filtered feeds optionally pre-filter with a regex before sending to Claude, or always send all items?
- **Q-007:** How should the News tab organize items within each feed — by date, by category, or configurable?
- ~~**Q-008:** Resolved — no `ai_status` field; items Claude does not return simply have no `ai_filtered_views` row and do not surface in the filtered view.~~
