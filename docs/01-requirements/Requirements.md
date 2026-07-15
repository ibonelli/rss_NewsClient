# Requirements — pelis-feed

## 1) Goal
- The system shall automatically ingest movie data from the YTS RSS feed and news from configurable RSS/Atom news feeds, provide on-demand rating enrichment for movies, and serve a filterable, read-tracked web-based view grouped appropriately for each content type. All news feeds expose a JSON export/import workflow so an external tool can classify items without any direct AI integration inside the application.
- The system shall also ingest TV series episode data from the EZTV RSS feed, parse season/episode identifiers, group quality variants, and serve a browsable Series tab with the same read-tracking pattern as movies.
- The system shall ingest articles from configurable design RSS feeds (e.g., Designboom), extracting title, summary, and image, and serve them in a dedicated Design tab with card-style layout and read/unread tracking.

## 2) Personas / Users
- Persona A: Self (sole user) — wants to discover quality movies, track TV series episodes, read relevant news, and browse design inspiration without manual browsing

## 3) Functional Requirements

### Ingestion — Movies
- **FR-001:** The system MUST fetch RSS data from `https://yts.ag/rss` every ~2 hours via a scheduled process.
- **FR-002:** The system MUST store ingested movie data in a SQLite or MySQL database.
- **FR-003:** The system MUST handle duplicate entries (same name or same torrent URL) by appending new information (e.g., different quality/resolution) to the existing movie record rather than creating a new entry.
- **FR-008:** The system MUST track feed health by recording the timestamp of the last successful fetch for each configured feed (movie, series, and news).
- **FR-078:** The system MUST correctly extract each genre as a standalone tag from the `<description>` HTML, with no genre value ever containing fused Size/Runtime/plot text (see ADR-015).
- **FR-079:** The system MUST extract, when present in the description: Size (stored per quality/format variant as `{quality, size}`, not as a flat movie field or genre), Runtime (raw string, not normalized), and Plot (full untruncated synopsis). Absence of any of these MUST NOT cause the entry to be rejected.
- **FR-080:** `Movie.qualities` MUST be a JSON array of `{quality, size}` objects; merging a duplicate movie MUST union quality variants by `quality` name without discarding an existing variant's `size` (mirrors the existing `SeriesEpisode.qualities` merge pattern).

### Ingestion — Series
- **FR-039:** The system MUST fetch RSS data from `https://eztv.re/ezrss.xml` on the same ~2h cron schedule as movies.
- **FR-040:** The system MUST parse each RSS entry to extract: series name, season number, episode number, quality/resolution, and torrent download page URL. (IMDb ID is not present in the EZTV feed — see ADR-010.)
- **FR-041:** Deduplication is two-level: (a) series title uniqueness in the `series` table; (b) episode uniqueness by `(series_id, season, episode)` in the `series_episodes` table. New quality variants for an existing episode MUST be merged rather than duplicated.
- **FR-042:** The system MUST store series data in two dedicated tables: `series` (one row per unique title) and `series_episodes` (one row per unique title+season+episode).
- **FR-043:** Feed health tracking MUST extend to the EZTV series feed.
- **FR-053:** When a new episode is ingested for a series that is already marked `is_ignored = true`, the new episode MUST inherit `is_ignored` at the series level (no per-episode flag needed — ignore is a series-level attribute).

### Ingestion — News
- **FR-019:** The system MUST support ingesting from news RSS/Atom feeds configurable in `config.yaml`, each with a `type` field: `unfiltered` or `filtered`. (The `ai_filtered` type has been removed — see Change-Log M10.)
- **FR-020:** News feeds MUST be fetched on the same ~2h cron cycle as the movie feed.
- **FR-021:** Unfiltered news feeds MUST store all fetched items without filtering.
- **FR-022:** Filtered news feeds MUST store ALL fetched items. Items matching the configured regex MUST have the matching filter identifier recorded in a dedicated `matched_filter` field; non-matching items have this field null.
- ~~**FR-023:** Removed — the `ai_filtered` feed type and `ai_filtered_views` table are no longer used by the application.~~
- ~~**FR-024:** Removed — Claude CLI prompt configuration is no longer applicable.~~
- **FR-025:** Feed health tracking MUST extend to all news feeds, recording last successful fetch per feed.

### Ingestion — Design
- **FR-060:** The system MUST support ingesting from design RSS feeds configurable in `config.yaml` under `design_feeds:`, each with a `name` and `url` field.
- **FR-061:** Design feeds MUST be fetched on the same ~2h cron cycle as movie, series, and news feeds.
- **FR-062:** Each design item MUST store: title, article URL, publication date (nullable), source feed name, summary (plain text), image URL (nullable), ingestion timestamp, and read status.
- **FR-063:** Image URL MUST be extracted best-effort from the RSS entry in this priority order: (1) `<media:content url>`, (2) `<enclosure url>`, (3) first `<img src>` in `<description>` HTML. If no image is found, `image_url` is stored as null; no placeholder is shown.
- **FR-064:** Deduplication for design items MUST be by `(url, feed_name)` — duplicate items MUST be skipped on re-ingestion (idempotent).
- **FR-065:** Feed health tracking MUST extend to all configured design feeds, one `feed_health` row per feed.
- **FR-066:** The system MUST send an email alert if any design feed is unreachable for more than 24 hours (same threshold as all other feeds).

### Enrichment — Movies
- **FR-009:** The system MUST extract any ratings provided natively by the RSS feed during ingestion (if available).
- **FR-010:** The web application MUST provide a per-movie "refresh ratings" button that triggers on-demand enrichment from a free external source (OMDb, imdbapi.dev, TMDb, or scraping).
- **FR-011:** On-demand enrichment MUST fetch IMDb rating, Rotten Tomatoes expert rating, and RT audience rating when triggered.
- **FR-012:** The system SHOULD gracefully handle enrichment failures (source unavailable) and display an error state to the user without crashing.

### News Data Model
- **FR-026:** Each stored `news_items` row MUST carry: title, URL, publication date, source feed name, full content, ingestion timestamp, read status, and `matched_filter` (nullable; populated only for filtered feeds when a regex match occurs).
~~**FR-027:** Removed — the `ai_filtered_views` table is a legacy DB table, retained on disk but no longer used by the application.~~

### Web Application — Movies
- **FR-004:** The system MUST provide a local web application (FastAPI) that serves the filtered movie view dynamically from the database.
- **FR-005:** The web application MUST filter movies using configurable rules based on genre and ratings (IMDb, RT expert, RT public), where rating thresholds vary by genre.
- **FR-006:** The web application MUST group movies with the same name (or same torrent URL), showing available qualities/resolutions together.
- **FR-013:** The view MUST be organized by year, from 2026 down to 2021 (6 years from today), with a separate section per year.
- **FR-014:** Movies older than the 6-year window MUST appear in a summarized section with stricter rating filtering.
- **FR-015:** Within each year section, movies MUST be ordered by genre priority: Action and Romantic Comedies first, Documentaries last, other genres in between.
- **FR-016:** Filtering configuration MUST be stored in a config file (not hardcoded), adjustable without restarting the web application.

### Web Application — Series
- **FR-044:** The web application MUST provide a Series tab, distinct from Movies and News.
- **FR-045:** The Series tab MUST group episodes by series title → season → episode. Each series title MUST link to its IMDb page (direct link if `imdb_id` is known; IMDb title-search URL otherwise). Each quality variant within an episode row MUST link to its torrent download page.
- **FR-046:** The Series tab MUST provide per-episode read/unread tracking persisted in the `series_episodes` table, independent per episode.
- **FR-047:** The system MUST send an email alert if the EZTV feed is unreachable for more than 24 hours (reusing existing alerter logic).
- **FR-051:** The Series tab MUST provide an Ignore/Unignore toggle at the series title level. Setting `is_ignored = true` moves the series to the Ignored view; clearing it returns it to the Following view. Ignored status MUST be persisted and survive app restart.
- **FR-052:** The Series tab MUST provide two independent toggle buttons controlling the displayed episode list, without a page reload:
  - **Unread/Read toggle** — Unread (default): episodes with `is_read=false`; Read: episodes with `is_read=true`
  - **Following/Ignored toggle** — Following (default): non-ignored series; Ignored: ignored series
  - Default on load: Unread + Following. A series title appears only if it has at least one episode matching the read filter.
- **FR-053:** When new episodes are ingested for a series whose existing episodes are marked ignored, the new episodes MUST inherit the ignored status automatically.
- **FR-054:** The Ignore toggle MUST operate at the series title level — a single action sets or clears `is_ignored` on every episode row sharing that title.

### Web Application — News
- **FR-028:** The web application MUST provide a separate "News" tab, distinct from the Movies tab.
- **FR-029:** Each news feed view MUST provide a **Read/Unread toggle** (Unread default) that switches between items with `is_read=false` and items with `is_read=true` without a page reload. Per-item "Mark Read" (in Unread view) and "Mark Unread" (in Read view) buttons MUST remove the item from the current view immediately on click, persisted in DB, survives restart.
- **FR-030:** For filtered feeds, the News tab MUST show only items where `matched_filter` is not null, displaying the matched filter name/pattern alongside each item.
~~**FR-031:** Removed — the `ai_filtered` feed type has been eliminated.~~
- ~~**FR-032:** Removed — the raw `news_items` sub-view for AI-filtered feeds is no longer provided.~~

### Web Application — Design
- **FR-067:** The web application MUST provide a Design tab, distinct from Movies, Series, and News.
- **FR-068:** The Design tab MUST display items from all configured design feeds; feeds MUST be selectable within the tab (e.g., per-feed sub-view or tab switcher).
- **FR-069:** Each design feed view MUST display items as cards containing: image (if `image_url` is not null), title linked to the article URL, and summary text. Card layout MUST be visually similar to the Movies card layout (image left, content right).
- **FR-070:** The Design tab MUST provide a Read/Unread toggle (Unread default) that switches between `is_read=false` and `is_read=true` items without a page reload.
- **FR-071:** Per-item "Mark Read" (Unread view) and "Mark Unread" (Read view) buttons MUST remove the item from the current view immediately on click, persisted in DB.
- **FR-072:** A "Mark All Read" button MUST appear only when the Unread toggle is active; it marks all currently unread items for the selected feed as read and clears the view.
- **FR-073:** There is NO rating filter and NO content filter for design items — all ingested items are shown regardless of content. The Flagged/Un-Flagged toggle from movies MUST NOT appear.
- **FR-074:** There is NO export feature for design feeds.

### Web Application — Navigation / URL Routing
- **FR-075:** The web application MUST expose a distinct, bookmarkable URL per feed type: `/movies`, `/series`, `/news`, `/design`. Navigating directly to any of these URLs MUST load the app with the corresponding tab active.
- **FR-076:** The News and Design tabs MUST additionally support deep-linking to a specific configured feed via `/news/{feed_name}` and `/design/{feed_name}`, where `feed_name` matches a `name` entry under `news_feeds` / `design_feeds` in `config.yaml` (URL-encoded).
- **FR-077:** Clicking a tab or selecting a News/Design sub-feed MUST update the browser URL to match (without a full page reload), and browser back/forward MUST restore the previously active tab/feed. Visiting an unrecognized path MUST fall back to the Movies tab.

### Export (All News Feeds)
- **FR-033:** The web application MUST expose `GET /api/news/{feed}/export` for any configured news feed, returning a downloadable JSON file containing only `unread_items` (all `news_items` rows for that feed where `is_read = false`). Each item MUST include its `news_items.id`, title, URL, publication date, and content.
- ~~**FR-034:** Removed — the import endpoint (`POST /api/news/{feed}/import`) is no longer provided.~~
- **FR-035:** The News tab MUST provide an **Export Unread** button on every news feed view. There is no Import control.
- ~~**FR-036:** Removed — no import UI control.~~

### Web Application — Movie View Controls
- **FR-037:** The Movies tab MUST provide two independent toggle buttons that combine to control the displayed movie list, without a page reload:
  - **Read/Unread toggle** — switches between unread movies (default) and read movies
  - **Flagged/Un-Flagged toggle** — switches between movies that pass the rating/genre filter ("Flagged", default) and movies that fail it ("Un-Flagged")
  - The four combinations (Unread+Flagged, Unread+Un-Flagged, Read+Flagged, Read+Un-Flagged) cover all movie states. Default on load: Unread + Flagged.
- **FR-055:** Movies with no ratings (all null — not yet enriched) MUST appear in the **Flagged** state. They pass the filter by default until enriched.
- **FR-056:** The Flagged/Un-Flagged split MUST use the same runtime logic and config thresholds as the existing filter — no `is_flagged` column is stored; the split is computed at query time.
- **FR-038:** The movie title MUST be a clickable link to IMDb — directly to `https://www.imdb.com/title/{imdb_id}/` when `imdb_id` is known, falling back to an IMDb title+year search URL for unenriched movies. The IMDb rating badge MUST be plain text (not a link). RT (Tomatometer and Audience) badges MUST link to a Rotten Tomatoes title search. RT badges with no rating (N/A) MUST NOT be links.

### Mark All as Read
- **FR-048:** The Movies tab MUST provide a "Mark All Read" button when the **Unread** toggle is active. It marks only the currently visible movies (respecting the current Flagged/Un-Flagged state) as read, and removes them from the view. The button MUST NOT appear when the Read toggle is active.
- **FR-049:** The Series tab MUST provide a "Mark All Read" button when the **Unread** toggle is active. It marks only the unread episodes of series in the currently visible Following or Ignored group as read and removes them from the view. The button MUST NOT appear when the Read toggle is active.
- **FR-050:** Every news feed view MUST provide a "Mark All Read" button when the **Unread** toggle is active. It marks all currently unread items for that feed as read and clears the view. The button MUST NOT appear when the Read toggle is active.

### Read Tracking
- **FR-017:** The web application MUST provide a UI mechanism (button/toggle) to mark movies as "already read/seen" so they are excluded from the view.
- **FR-018:** Read-tracking status MUST be persisted in the database and survive application restarts.

### Alerting
- **FR-007:** The system MUST send an email alert via local SMTP if any configured feed (movie, series, or news) is unreachable for more than 24 hours.

## 4) Non-Functional Requirements (NFRs)
- **NFR-001 (Availability):** The scheduler MUST tolerate transient feed failures without crashing — retry on next cycle.
- **NFR-002 (Performance):** Report generation SHOULD complete within 30 seconds for up to 10,000 stored movies.
- **NFR-003 (Maintainability):** Code MUST be written in Python with clear separation between ingestion, enrichment, and report generation.
- **NFR-004 (Cost):** The system MUST NOT use paid APIs for movie or series metadata enrichment.
- ~~**NFR-005:** Removed — Claude CLI timeout is no longer applicable.~~
- **NFR-006 (Export Observability):** The application SHOULD log the number of items included in each export request.

## 5) Data Requirements
- **Movies:** title, year, genre(s), torrent URL, quality/resolution, IMDb ID (from enrichment), IMDb rating, RT expert rating, RT audience rating, poster URL, feed entry date, enrichment date, read status
- **Series (`series` table):** series title (unique), IMDb ID (nullable), is_ignored flag
- **Series episodes (`series_episodes` table):** FK → series, season number, episode number, quality variants (JSON list of `{quality, torrent_page_url}`), RSS entry date, ingestion timestamp, is_read flag, ignored status
- **News — `news_items` (all feed types):** title, URL, publication date, source feed name, full content, ingestion timestamp, read status, matched_filter (nullable)
- **News — `ai_filtered_views`:** legacy table retained on disk; no longer written or read by the application
- **Design — `design_items`:** title, article URL, publication date (nullable), source feed name, summary (plain text), image URL (nullable), ingestion timestamp, read status
- Retention: indefinite (database on disk)
- PII classification: None

## 6) Integration Requirements
- Upstream: YTS RSS feed (`https://yts.ag/rss`), EZTV RSS feed (`https://eztv.re/ezrss.xml`), configurable news RSS/Atom feeds, configurable design RSS feeds (e.g., `https://www.designboom.com/feed/`), TMDb/OMDb/imdbapi.dev or scraping for movie ratings
- Downstream: Local SMTP for email alerts
- Contracts: RSS XML format (subject to change without notice); export JSON schema defined in FR-033

## 7) Acceptance Criteria
- **AC-001:** Running the scheduler for 24h produces at least one successful fetch and stores data in the database.
- **AC-002:** The Movies tab shows two independent toggles (Read/Unread and Flagged/Un-Flagged). All four combinations work correctly, each grouped by year and genre priority, without page reload.
- **AC-003:** Changing the filter config and reloading moves a movie between Flagged and Un-Flagged without any DB change.
- **AC-004:** Marking a movie as read removes it from the Unread view; switching to the Read toggle shows it in the correct Flagged/Un-Flagged group.
- **AC-005:** Simulating feed downtime >24h triggers an email alert.
- **AC-006:** Movies have enriched ratings from at least one external source.
- **AC-007:** Unfiltered news feeds store all fetched items; read/unread status survives app restart.
- **AC-008:** Filtered news feeds store all items; only items with a non-null `matched_filter` appear in the News tab, with the filter name displayed.
- **AC-009:** For any news feed, clicking Export downloads a JSON file containing unread `news_items` rows. No import control is present.
- **AC-010:** The web UI News tab is accessible and displays news items independently of the Movies tab.
- ~~**AC-011:** Removed — AI-filtered feed type eliminated.~~
- ~~**AC-012:** Removed — AI-filtered feed type eliminated.~~
- **AC-013:** Series episodes from the EZTV feed appear in the Series tab, grouped by series title → season → episode.
- **AC-014:** Multiple quality variants of the same episode are merged into a single `series_episodes` row, each with a working torrent download page link.
- **AC-015:** Each series title in the UI links to its IMDb page (direct when `imdb_id` is known; search URL otherwise).
- **AC-016:** Read-tracking per episode is persisted in `series_episodes` and survives app restart.
- **AC-017:** An email alert fires if the EZTV feed is unreachable for > 24 hours.
- **AC-018:** Ignoring a series removes it from the Following view; it appears only when the Ignored toggle is active.
- **AC-019:** New episodes ingested for an ignored series do not appear in the Following views — they are accessible only via the Ignored toggle.
- **AC-020:** Switching the Unread/Read and Following/Ignored toggles independently produces the correct filtered episode list without a page reload.

- **AC-021:** Design items from configured design feeds appear in the Design tab, displayed as cards with image (if available), title linked to the article URL, and summary.
- **AC-022:** Items without an image in the RSS feed appear as cards with title and summary only — no placeholder is shown.
- **AC-023:** The Read/Unread toggle works correctly for design items; read status survives app restart.
- **AC-024:** "Mark All Read" on the Unread view clears all unread items for the selected feed; no export button is present.
- **AC-025:** An email alert fires if any configured design feed is unreachable for >24 hours.
- **AC-026:** Multiple design feeds configured in `config.yaml` are all ingested and selectable in the Design tab independently.

## 8) Open Questions
- **Q-001:** Which free rating source is most reliable/complete for movies? (TMDb, OMDb free tier, imdbapi.dev, scraping?)
- ~~**Q-002:** Resolved — see ADR-001 (FastAPI web app)~~
- **Q-003:** What are the initial genre-specific rating thresholds? (can iterate via config)
- **Q-004:** What genre ordering should be used between "Action/RomCom" (first) and "Documentary" (last)?
- ~~**Q-005:** Resolved — Export schema defined in FR-033–FR-034.~~
- ~~**Q-006:** Resolved — pre-filtering before Claude is no longer applicable.~~
- **Q-007:** How should the News tab organize items within each feed — by date, by category, or configurable?
- ~~**Q-008:** Resolved — no `ai_status` field; items Claude does not return simply have no `ai_filtered_views` row.~~
- **Q-009:** What is the exact EZTV RSS XML structure? (title format, available fields — needs live inspection before implementing the parser)
- **Q-010:** How should entries without a valid S##E## match be handled — silently dropped, stored as-is, or logged?
- **Q-011:** Is the IMDb ID provided per-episode entry in the EZTV RSS feed, or per-series? (Determines whether IMDb ID is stored at the series or episode level — needs live feed inspection alongside Q-009.)
