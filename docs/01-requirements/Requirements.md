# Requirements — pelis-feed

## 1) Goal
- The system shall automatically ingest movie data from the YTS RSS feed, provide on-demand rating enrichment, and serve a filterable web-based view grouped by year and genre, with read-tracking capability.

## 2) Personas / Users
- Persona A: Self (sole user) — wants to discover quality movies without manual browsing

## 3) Functional Requirements

### Ingestion
- **FR-001:** The system MUST fetch RSS data from `https://yts.ag/rss` every ~2 hours via a scheduled process.
- **FR-002:** The system MUST store ingested movie data in a SQLite or MySQL database.
- **FR-003:** The system MUST handle duplicate entries (same name or same torrent URL) by appending new information (e.g., different quality/resolution) to the existing movie record rather than creating a new entry.
- **FR-008:** The system MUST track feed health by recording the timestamp of the last successful fetch.

### Enrichment
- **FR-009:** The system MUST extract any ratings provided natively by the RSS feed during ingestion (if available).
- **FR-010:** The web application MUST provide a per-movie "refresh ratings" button that triggers on-demand enrichment from a free external source (OMDb, imdbapi.dev, TMDb, or scraping).
- **FR-011:** On-demand enrichment MUST fetch IMDb rating, Rotten Tomatoes expert rating, and RT audience rating when triggered.
- **FR-012:** The system SHOULD gracefully handle enrichment failures (source unavailable) and display an error state to the user without crashing.

### Web Application (Report & Read-Tracking)
- **FR-004:** The system MUST provide a local web application (FastAPI) that serves the filtered movie view dynamically from the database.
- **FR-005:** The web application MUST filter movies using configurable rules based on genre and ratings (IMDb, RT expert, RT public), where rating thresholds vary by genre.
- **FR-006:** The web application MUST group movies with the same name (or same torrent URL), showing available qualities/resolutions together.
- **FR-013:** The view MUST be organized by year, from 2026 down to 2021 (6 years from today), with a separate section per year.
- **FR-014:** Movies older than the 6-year window MUST appear in a summarized section with stricter rating filtering.
- **FR-015:** Within each year section, movies MUST be ordered by genre priority: Action and Romantic Comedies first, Documentaries last, other genres in between.
- **FR-016:** Filtering configuration MUST be stored in a config file (not hardcoded), adjustable without restarting the web application.

### Read Tracking
- **FR-017:** The web application MUST provide a UI mechanism (button/toggle) to mark movies as "already read/seen" so they are excluded from the view.
- **FR-018:** Read-tracking status MUST be persisted in the database and survive application restarts.

### Alerting
- **FR-007:** The system MUST send an email alert via local SMTP if the RSS feed is unreachable for more than 24 hours.

## 4) Non-Functional Requirements (NFRs)
- **NFR-001 (Availability):** The scheduler MUST tolerate transient feed failures without crashing — retry on next cycle.
- **NFR-002 (Performance):** Report generation SHOULD complete within 30 seconds for up to 10,000 stored movies.
- **NFR-003 (Maintainability):** Code MUST be written in Python with clear separation between ingestion, enrichment, and report generation.
- **NFR-004 (Cost):** The system MUST NOT use paid APIs for enrichment.

## 5) Data Requirements
- Data elements: movie title, year, genre(s), torrent URL, quality/resolution, IMDb rating, RT expert rating, RT audience rating, poster URL, feed entry date, enrichment date, read status
- Retention: indefinite (database on disk)
- PII classification: None

## 6) Integration Requirements
- Upstream: YTS RSS feed (`https://yts.ag/rss`), TMDb/OMDb/imdbapi.dev or scraping for ratings
- Downstream: Local SMTP for email alerts
- Contracts: RSS XML format (subject to change without notice)

## 7) Acceptance Criteria
- **AC-001:** Running the scheduler for 24h produces at least one successful fetch and stores data in the database.
- **AC-002:** Report HTML contains movies grouped by name, sectioned by year, ordered by genre priority.
- **AC-003:** Changing filter config and regenerating report produces different output.
- **AC-004:** Marking a movie as read and regenerating excludes it from the report.
- **AC-005:** Simulating feed downtime >24h triggers an email alert.
- **AC-006:** Movies have enriched ratings from at least one external source.

## 8) Open Questions
- **Q-001:** Which free rating source is most reliable/complete? (TMDb, OMDb free tier, imdbapi.dev, scraping?)
- ~~**Q-002:** Resolved — see ADR-001 (FastAPI web app)~~
- **Q-003:** What are the initial genre-specific rating thresholds? (can iterate via config)
- **Q-004:** What genre ordering should be used between "Action/RomCom" (first) and "Documentary" (last)?
