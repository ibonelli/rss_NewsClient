# Requirements — pelis-feed

## 1) Goal
- The system shall automatically ingest movie data from the YTS RSS feed and news from configurable RSS/Atom news feeds, provide on-demand rating enrichment for movies, and serve a filterable, read-tracked web-based view grouped appropriately for each content type. All news feeds expose a JSON export/import workflow so an external tool can classify items without any direct AI integration inside the application.
- The system shall also ingest TV series episode data from the EZTV RSS feed, parse season/episode identifiers, group quality variants, and serve a browsable Series tab with the same read-tracking pattern as movies.

## 2) Personas / Users
- Persona A: Self (sole user) — wants to discover quality movies, track TV series episodes, and read relevant news without manual browsing

## 3) Functional Requirements

### Ingestion — Movies
- **FR-001:** The system MUST fetch RSS data from `https://yts.ag/rss` every ~2 hours via a scheduled process.
- **FR-002:** The system MUST store ingested movie data in a SQLite or MySQL database.
- **FR-003:** The system MUST handle duplicate entries (same name or same torrent URL) by appending new information (e.g., different quality/resolution) to the existing movie record rather than creating a new entry.
- **FR-008:** The system MUST track feed health by recording the timestamp of the last successful fetch for each configured feed (movie, series, and news).

### Ingestion — Series
- **FR-039:** The system MUST fetch RSS data from `https://eztv.re/ezrss.xml` on the same ~2h cron schedule as movies.
- **FR-040:** The system MUST parse each RSS entry to extract: series name, season number, episode number, quality/resolution, and torrent download page URL. (IMDb ID is not present in the EZTV feed — see ADR-010.)
- **FR-041:** Deduplication is two-level: (a) series title uniqueness in the `series` table; (b) episode uniqueness by `(series_id, season, episode)` in the `series_episodes` table. New quality variants for an existing episode MUST be merged rather than duplicated.
- **FR-042:** The system MUST store series data in two dedicated tables: `series` (one row per unique title) and `series_episodes` (one row per unique title+season+episode).
- **FR-043:** Feed health tracking MUST extend to the EZTV series feed.
- **FR-053:** When a new episode is ingested for a series that is already marked `is_ignored = true`, the new episode MUST inherit `is_ignored` at the series level (no per-episode flag needed — ignore is a series-level attribute).

### Ingestion — News
- **FR-019:** The system MUST support ingesting from news RSS/Atom feeds configurable in `config.yaml`, each with a `type` field: `unfiltered`, `filtered`, or `ai_filtered`.
- **FR-020:** News feeds MUST be fetched on the same ~2h cron cycle as the movie feed.
- **FR-021:** Unfiltered news feeds MUST store all fetched items without filtering.
- **FR-022:** Filtered news feeds MUST store ALL fetched items. Items matching the configured regex MUST have the matching filter identifier recorded in a dedicated `matched_filter` field; non-matching items have this field null.
- **FR-023:** AI-filtered news feeds MUST store all fetched items in `news_items`. The application MUST NOT invoke any AI tool directly; AI classification is handled externally via the export/import workflow (see FR-033–FR-036), which is available for all news feed types.
- ~~**FR-024:** Removed — Claude CLI prompt configuration is no longer applicable.~~
- **FR-025:** Feed health tracking MUST extend to all news feeds, recording last successful fetch per feed.

### Enrichment — Movies
- **FR-009:** The system MUST extract any ratings provided natively by the RSS feed during ingestion (if available).
- **FR-010:** The web application MUST provide a per-movie "refresh ratings" button that triggers on-demand enrichment from a free external source (OMDb, imdbapi.dev, TMDb, or scraping).
- **FR-011:** On-demand enrichment MUST fetch IMDb rating, Rotten Tomatoes expert rating, and RT audience rating when triggered.
- **FR-012:** The system SHOULD gracefully handle enrichment failures (source unavailable) and display an error state to the user without crashing.

### News Data Model
- **FR-026:** Each stored `news_items` row MUST carry: title, URL, publication date, source feed name, full content, ingestion timestamp, read status, and `matched_filter` (nullable; populated only for filtered feeds when a regex match occurs).
- **FR-027:** The `ai_filtered_views` table MUST contain: source feed name, title, URL, publication date, category (AI-assigned), summary (AI-generated), tags (AI-generated list), read status, keep-as-context flag, ingestion timestamp, and a `source_item_id` foreign key referencing the originating `news_items` row.

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
- **FR-051:** The Series tab MUST provide an Ignore/Unignore toggle at the series title level. Ignored series MUST be hidden from the default (Unread) and All views.
- **FR-052:** The Series tab MUST provide three views selectable by the user: **Unread** (default — non-ignored series with at least one unread episode), **All** (non-ignored series, all episodes regardless of read status), **Ignored** (only ignored series).
- **FR-051:** The Series tab MUST provide a per-series "Ignore" toggle that prevents all episodes of that series from appearing in the default (Filtered) view. Ignored status MUST be persisted in the database and survive app restart.
- **FR-052:** The Series tab MUST provide three sub-views: **Filtered** (default, unread AND not ignored), **All** (unread including ignored), and **Read** (all read entries, not-ignored first then ignored).
- **FR-053:** When new episodes are ingested for a series whose existing episodes are marked ignored, the new episodes MUST inherit the ignored status automatically.
- **FR-054:** The Ignore toggle MUST operate at the series title level — a single action sets or clears `is_ignored` on every episode row sharing that title.

### Web Application — News
- **FR-028:** The web application MUST provide a separate "News" tab, distinct from the Movies tab.
- **FR-029:** The news view MUST provide per-item read/unread tracking with behavior identical to movies (persisted in DB, survives restart).
- **FR-030:** For filtered feeds, the News tab MUST show only items where `matched_filter` is not null, displaying the matched filter name/pattern alongside each item.
- **FR-031:** For AI-filtered feeds, the News tab MUST display items from the `ai_filtered_views` table, showing category, summary, and tags. Read/unread tracking for AI-filtered feeds MUST be applied to `ai_filtered_views` rows.
- **FR-032:** For AI-filtered feeds, the News tab MUST also provide a sub-view displaying the full raw `news_items` for that feed, allowing the user to browse unprocessed items alongside the AI-filtered view.

### Export / Import (All News Feeds)
- **FR-033:** The web application MUST expose `GET /api/news/{feed}/export` for any configured news feed, returning a downloadable JSON file with two sections: `unread_items` (all `news_items` rows for that feed where `is_read = false`) and `context_items` (all `ai_filtered_views` rows for that feed where `keep_as_context = true`). Each item in `unread_items` MUST include its `news_items.id` so the import can reference it.
- **FR-034:** The web application MUST expose `POST /api/news/{feed}/import` for any configured news feed, accepting a JSON payload in the `ai_filtered_views` format (title, URL, publication date, category, summary, tags, and `source_item_id` referencing the originating `news_items.id`). On import, ALL existing `ai_filtered_views` rows for that feed MUST be deleted and replaced with the imported rows.
- **FR-035:** The News tab MUST provide Export and Import UI controls on every news feed view (regardless of type).
- **FR-036:** The Import control MUST submit a local JSON file to `FR-034` and refresh the view on success.

### Web Application — Movie View Controls
- **FR-037:** The Movies tab MUST provide two independent toggle buttons that combine to control the displayed movie list, without a page reload:
  - **Read/Unread toggle** — switches between unread movies (default) and read movies
  - **Flagged/Un-Flagged toggle** — switches between movies that pass the rating/genre filter ("Flagged", default) and movies that fail it ("Un-Flagged")
  - The four combinations (Unread+Flagged, Unread+Un-Flagged, Read+Flagged, Read+Un-Flagged) cover all movie states. Default on load: Unread + Flagged.
- **FR-055:** Movies with no ratings (all null — not yet enriched) MUST appear in the **Flagged** state. They pass the filter by default until enriched.
- **FR-056:** The Flagged/Un-Flagged split MUST use the same runtime logic and config thresholds as the existing filter — no `is_flagged` column is stored; the split is computed at query time.
- **FR-038:** IMDb and RT rating badges MUST be clickable links. For enriched movies (where `imdb_id` is known), the IMDb badge MUST link directly to `https://www.imdb.com/title/{imdb_id}/`. When `imdb_id` is not yet known, the badge MUST fall back to an IMDb title-search URL. RT badges MUST link to a Rotten Tomatoes search for the movie title. Badges with no rating (N/A) MUST NOT be links.

### Mark All as Read
- **FR-048:** The Movies tab MUST provide a "Mark All Read" button when the **Unread** toggle is active. It marks only the currently visible movies (respecting the current Flagged/Un-Flagged state) as read, and removes them from the view. The button MUST NOT appear when the Read toggle is active.
- **FR-049:** The Series tab MUST provide a "Mark All Read" button that marks every unread `series_episodes` row as read and removes them from the Unread view in a single action.
- **FR-050:** Every news feed view MUST provide a "Mark All Read" button that marks all `news_items` (and any `ai_filtered_views`) for that feed as read in a single action.

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
- **NFR-006 (Export/Import Observability):** The application SHOULD log the number of items included in each export request and the number of `ai_filtered_views` rows persisted on each import.

## 5) Data Requirements
- **Movies:** title, year, genre(s), torrent URL, quality/resolution, IMDb ID (from enrichment), IMDb rating, RT expert rating, RT audience rating, poster URL, feed entry date, enrichment date, read status
- **Series (`series` table):** series title (unique), IMDb ID (nullable), is_ignored flag
- **Series episodes (`series_episodes` table):** FK → series, season number, episode number, quality variants (JSON list of `{quality, torrent_page_url}`), RSS entry date, ingestion timestamp, is_read flag, ignored status
- **News — `news_items` (all feed types):** title, URL, publication date, source feed name, full content, ingestion timestamp, read status, matched_filter (nullable)
- **News — `ai_filtered_views` (AI-filtered feeds only):** source feed name, title, URL, publication date, category, summary, tags (list), read status, keep-as-context flag, ingestion timestamp, source_item_id (FK → news_items)
- Retention: indefinite (database on disk)
- PII classification: None

## 6) Integration Requirements
- Upstream: YTS RSS feed (`https://yts.ag/rss`), EZTV RSS feed (`https://eztv.re/ezrss.xml`), configurable news RSS/Atom feeds, TMDb/OMDb/imdbapi.dev or scraping for movie ratings
- Downstream: Local SMTP for email alerts; external AI tool (unconstrained — operated separately, consumes export JSON, produces import JSON)
- Contracts: RSS XML format (subject to change without notice); export/import JSON schema defined in FR-033–FR-034

## 7) Acceptance Criteria
- **AC-001:** Running the scheduler for 24h produces at least one successful fetch and stores data in the database.
- **AC-002:** The Movies tab shows two independent toggles (Read/Unread and Flagged/Un-Flagged). All four combinations work correctly, each grouped by year and genre priority, without page reload.
- **AC-003:** Changing the filter config and reloading moves a movie between Flagged and Un-Flagged without any DB change.
- **AC-004:** Marking a movie as read removes it from the Unread view; switching to the Read toggle shows it in the correct Flagged/Un-Flagged group.
- **AC-005:** Simulating feed downtime >24h triggers an email alert.
- **AC-006:** Movies have enriched ratings from at least one external source.
- **AC-007:** Unfiltered news feeds store all fetched items; read/unread status survives app restart.
- **AC-008:** Filtered news feeds store all items; only items with a non-null `matched_filter` appear in the News tab, with the filter name displayed.
- **AC-009:** For any news feed, clicking Export downloads a JSON file containing unread `news_items` rows (with IDs) and `keep_as_context` `ai_filtered_views` rows. Uploading a valid import JSON replaces `ai_filtered_views` for that feed, and the results appear immediately in the News tab.
- **AC-010:** The web UI News tab is accessible and displays news items independently of the Movies tab.
- **AC-011:** For AI-filtered feeds, both the AI-filtered sub-view and the raw unprocessed sub-view are accessible in the News tab.
- **AC-012:** After import, each `ai_filtered_views` row carries a `source_item_id` that correctly references its originating `news_items` row.
- **AC-013:** Series episodes from the EZTV feed appear in the Series tab, grouped by series title → season → episode.
- **AC-014:** Multiple quality variants of the same episode are merged into a single `series_episodes` row, each with a working torrent download page link.
- **AC-015:** Each series title in the UI links to its IMDb page (direct when `imdb_id` is known; search URL otherwise).
- **AC-016:** Read-tracking per episode is persisted in `series_episodes` and survives app restart.
- **AC-017:** An email alert fires if the EZTV feed is unreachable for > 24 hours.
- **AC-018:** Ignoring a series hides it from the Unread and All views; it appears only in the Ignored view.
- **AC-019:** New episodes ingested for an ignored series are not shown in the Unread or All views.
- **AC-018:** Clicking "Ignore" on a series title removes it from the Filtered sub-view and keeps it visible in the All sub-view. Clicking "Unignore" reverses this.
- **AC-019:** The Read sub-view lists all read series, with not-ignored titles sorted before ignored titles.
- **AC-020:** Newly ingested episodes for an already-ignored series appear as ignored and are absent from the Filtered sub-view without any user action.

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
