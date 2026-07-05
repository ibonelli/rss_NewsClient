# Change Log — pelis-feed

## Unreleased

### Fixed — Movie Genre-Fusion Parsing Bug + Size/Runtime/Plot (ADR-015)
- Fixed `_DescriptionParser`/`_parse_entry` (`src/cli/fetcher.py`): the genre regex previously terminated only on a literal `Rating:` substring or end-of-string, which never matched again since `Rating:` appears *before* `Genre:` in the real YTS layout — this fused the last genre together with Size/Runtime/plot text (reported live example: "Crime 101" — last genre was `"Thriller Size: 1.26 GB Runtime: 2hr 20 min <full plot>"`). Genre is now bounded by a lookahead over every label that can actually follow it.
- Added Size, Runtime, and Plot extraction from the `<description>` HTML (previously discarded entirely): Size and Runtime are bounded by their own value shape; Plot is whatever text follows the last recognized label.
- `Movie.qualities` changes shape from a flat list of strings (`["1080p"]`) to `[{"quality": "1080p", "size": "1.26 GB"}]` — Size is a property of the quality/format, mirroring the existing `SeriesEpisode.qualities` pattern. `dedup.py:_merge_qualities` now unions by `quality` key (previously a flat string set-union).
- New `Movie.runtime` (raw string, e.g. `"2hr 20 min"`) and `Movie.plot` (full synopsis) columns.
- `tools/migrate_004_movie_runtime_plot.sh`: adds both columns, backfills legacy flat-string `qualities` to `{quality, size: null}` objects, and **repairs already-corrupted `genres`/`runtime`/`plot` on existing rows** by reconstructing the original text from what was stored (the corruption was a mis-split, not data loss) — fixed 30 of 40 existing movies in the live database, including the reported "Crime 101" row.
- `_movie_to_dict` (`routes.py`) and `MovieCard` (`app.js`) updated to serialize/render `runtime` and `plot`, and quality badges now show size (e.g. "1080p · 1.26 GB").
- New regression test `tests/test_fetcher.py` (stdlib `unittest`, no new dependency) covering the exact reported bug plus size/runtime-absent edge cases.
- See FR-078–FR-080

### Added — Per-Feed-Type URL Routes (ADR-014)
- FastAPI now serves the SPA shell at `/movies`, `/series`, `/news`, `/news/{feed_name}`, `/design`, `/design/{feed_name}` in addition to `/` (`routes.py:serve_spa_route`) — no per-route rendering, same `index.html` for all
- React frontend (`app.js`) gained a small History-API router: `parseLocation()` derives `{tab, feedName}` from `window.location.pathname` (falls back to Movies on unrecognized paths); `navigate()`/`replaceLocation()` push/replace the URL; a `popstate` listener keeps state in sync with browser back/forward
- Tab buttons and News/Design feed selection now update the URL bar; direct navigation to any of the above URLs loads with the right tab/feed active
- See FR-075–FR-077

### Added — M11: Design Feed (Planned)
- New `design_items` table: `feed_name`, `title`, `url` (UNIQUE per feed), `published_at`, `summary` (plain text), `image_url` (nullable), `ingested_at`, `is_read`
- `design_feeds:` config block — list of `{name, url}` entries; same pattern as `news_feeds:`
- CLI Ingester extended to fetch all configured design feeds; image extracted best-effort from `<media:content>` → `<enclosure>` → first `<img>` in description HTML; summary stored as plain text (HTML stripped)
- Feed health + 24h email alerting extended to design feeds
- `GET /api/design` — all configured design feeds with unread counts
- `GET /api/design/{feed_name}/items?read=false|true` — items filtered by read state
- `POST /api/design/items/{id}/read` and `/unread` — per-item read tracking
- `POST /api/design/{feed_name}/read-all` — mark all unread items for a feed as read
- Design tab in React frontend: card layout (image left, title + summary right); Read/Unread toggle; "Mark All Read" (Unread view only); no filter/flagging; no export

### Changed — Movie Title Styling
- `.movie-title`: font size 1rem → 1.2rem, weight 600 → 700, flex layout added (matches series title typography); gains `padding: 0.75rem 1rem`, `background: var(--bg-card)`, `border-bottom` to form a card-header section
- `.movie-title a`: accent color (`var(--accent)`) + no underline by default; hover adds underline and lightens to `var(--accent-hover)` (matches `.series-title a` rules)
- `.movie-body` (new): wraps genres/qualities/ratings/actions below the title; `background: var(--bg-secondary)` creates a two-tone card — title in `--bg-card` (#0f3460), content in `--bg-secondary` (#16213e), mirroring the series block pattern
- `.movie-info`: `padding` and `gap` removed (delegated to `.movie-title` and `.movie-body` respectively)

### Added — Series "Ignore All" Button
- `POST /api/series/ignore-all` — sets `is_ignored = True` on all non-ignored series; returns `{"ignored": count}`
- Series tab: "Ignore All" button in the toolbar; visible only when Not-Ignored view is active; clears the series list on success
- Behaviour mirrors "Mark All Read": shows `...` while in-flight, disabled during the request

### Added — M10: Drop ai_filtered Feed Type
- Remove `ai_filtered` as a valid feed type from config, backend, and frontend
- Feeds configured with `type: ai_filtered` will no longer be served or displayed
- `ai_filtered_views` table retained in DB schema (no migration); no longer read or written
- Remove `POST /api/news/views/{id}/read` and `/unread` endpoints
- Remove `AIFilteredView` from routes, imports, and frontend (`AIViewRow`, `AIFilteredFeedView`)
- `config.yaml.example` updated to document only `unfiltered` and `filtered` types
- `GET /api/news` no longer counts unread from `ai_filtered_views`
- `POST /api/news/{feed}/read-all` no longer marks `ai_filtered_views` rows

### Added — M9: News Feed Simplification + Read/Unread Toggle
- `GET /api/news/{feed}/items?read=false|true` — new `read` bool param (default `false`); UI shows only items matching the selected read state
- Per-item "Mark Read" (Unread view) and "Mark Unread" (Read view) buttons remove the item from the current view immediately on click
- "Mark All Read" button visible only when Unread toggle is active; marks all unread items for the feed
- **Removed**: `POST /api/news/{feed}/import` — import endpoint and Import UI button eliminated
- **Removed**: `GET /api/news/{feed}/raw` — raw sub-view for AI-filtered feeds eliminated
- **Removed**: `POST /api/news/views/{id}/keep` and `/unkeep` — Keep as Context feature eliminated
- `ai_filtered_views.keep_as_context` column retained in DB schema but no longer used by the application
- Export (`GET /api/news/{feed}/export`) simplified: returns only `unread_items` (no `context_items` section); always exports unread regardless of toggle state
- `FeedToolbar` component: Export button kept; Import button removed
- `ai_filter.sh` script affected: the import step no longer has an API endpoint to POST to

### Added — Series Two-Toggle View (Unread/Read × Not-Ignored/Ignored)
- `GET /api/series?read=false&ignored=false` — replaces old `?view=unread|all|ignored`; two independent bool params
  - `read` (bool, default `false`): `false` = unread episodes, `true` = read episodes
  - `ignored` (bool, default `false`): `false` = non-ignored series (Not-Ignored), `true` = ignored series
  - "All" view removed — the Read + Not-Ignored combination covers its content
- `POST /api/series/read-all?ignored=false|true` — scopes mark-all to the currently visible Not-Ignored or Ignored group only
- Series tab: two independent toggle buttons — **Unread/Read** and **Not-Ignored/Ignored**; default Unread + Not-Ignored
- Read view: per-episode "Mark Unread" button (mirrors Movie Read view)
- Ignore button shows on Not-Ignored view; Unignore button shows on Ignored view
- "Mark All Read" visible only when Unread toggle is active; scoped to the current Ignored state

### Added — M8: Movies Two-Toggle View
- `GET /api/movies?read=false&flagged=true` — replaces old `?filtered=bool` and the M8-interim `?view=...`
  - `read` (bool, default `false`): `false` = unread movies, `true` = read movies
  - `flagged` (bool, default `true`): `true` = passes rating/genre filter ("Flagged"), `false` = fails filter ("Un-Flagged")
- `POST /api/movies/read-all?flagged=true|false` — scopes mark-all to the currently visible Flagged or Un-Flagged set only
- No schema change — Flagged/Un-Flagged split computed at runtime from config thresholds (no `is_flagged` column)
- Unenriched movies (null ratings) appear in Flagged results (pass-by-default behaviour preserved)
- Movies tab: two independent toggle buttons — **Unread/Read** and **Flagged/Un-Flagged**; default Unread + Flagged
- "Mark All Read" visible only when Unread toggle is active; scoped to the current Flagged/Un-Flagged state

### Added — M7: Series Two-Table Split + Ignore
- `series` table: one row per unique title (`title` UNIQUE, `imdb_id` nullable, `is_ignored` bool)
- `series_episodes` table: one row per `(series_id, season, episode)`; FK → `series.id`; carries `qualities`, `feed_entry_date`, `ingested_at`, `is_read`
- Deduplication now two-level: upsert series title first, then upsert episode; `session.flush()` used between levels to populate `series.id` before the episode insert
- `is_ignored` at title level only — new episodes for an ignored series automatically inherit ignore status via JOIN at query time (no per-episode flag)
- `GET /api/series?view=unread|all|ignored` — three views (replaces old `filtered|all|read`)
  - `unread` (default): non-ignored series with at least one unread episode
  - `all`: non-ignored series, all episodes regardless of read status
  - `ignored`: only ignored series
- Response includes `series.id`, `imdb_url` (always present; IMDb title-search URL when `imdb_id` is null per ADR-010)
- `POST /api/series/{series_id}/ignore` and `/api/series/{series_id}/unignore` — PK-based (O(1) single row update)
- `POST /api/series/episodes/{episode_id}/read` and `/unread` — episode-level read tracking
- `POST /api/series/read-all` now marks `series_episodes.is_read`
- Series tab: view switcher (Unread / All / Ignored); Ignore/Unignore per title; Mark All Read hidden on Ignored view
- `clear_db.sh`: auto-detects old `series` schema (M6) and drops/recreates it; skips missing tables gracefully; calls `init_db` after clearing

---

### Changed — Export/Import universalised; Mark All Read added
- Export (`GET /api/news/{feed}/export`) and Import (`POST /api/news/{feed}/import`) now available for **all** news feed types, not just `ai_filtered`; `_get_ai_filtered_feed` type gate removed; raw endpoint (`GET /api/news/{feed}/raw`) similarly unrestricted
- `FeedToolbar` component (Export / Import Results / Mark All Read) now renders on every news feed view
- `POST /api/movies/read-all` — marks all unread movies as read; Movies tab toolbar gains "Mark All Read" button
- `POST /api/series/read-all` — marks all unread episodes as read; Series tab gains toolbar with count and "Mark All Read" button
- `POST /api/news/{feed}/read-all` — marks all `news_items` and `ai_filtered_views` for the feed as read

### Added — M6: Series Feed
- EZTV RSS ingestion (`https://eztv.re/ezrss.xml`) with S##E## parsing; handles both space- and dot-separated title formats
- `Series` DB table; deduplication merges quality variants by `title+season+episode`
- `GET /api/series` grouped by title → season → episode; IMDb search link per series title (EZTV feed has no IMDb ID); torrent page link per quality variant
- Read-tracking for series entries (`POST /api/series/{id}/read`, `/unread`)
- Feed health + email alerting extended to EZTV feed (`eztv_series`)
- `config.yaml` / `config.yaml.example`: `series_feed.url` key

### Added — UI / Enrichment improvements
- Movies tab: **Filtered / All toggle** — switches between rating-filtered view and full unread-movie list without page reload (`GET /api/movies?filtered=false`; FR-037)
- Movies tab: **IMDb rating badge** links directly to `https://www.imdb.com/title/{imdb_id}/` for enriched movies; falls back to IMDb title-search URL when `imdb_id` is not yet known (FR-038)
- Movies tab: **RT Tomatometer and Audience badges** link to Rotten Tomatoes search for the movie title (FR-038)
- Movies tab: **quality/resolution badges** (720p, 1080p, 2160p) are now clickable links to the torrent URL
- Movies tab: poster image widened to 300px (3× previous size); text panel minimum width widened to 440px

### Added — M5: News Feeds + Filter Processor
- CLI Ingester extended to fetch configurable news RSS/Atom feeds after the movie feed; all items stored to `news_items`; `FeedHealth` updated per news feed
- CLI Filter Processor (`src/cli/filter.py`): syncs `filters` table from config; regex-flags matching `news_items` via `matched_filter_id` — never deletes rows; no AI invocation
- FastAPI Web UI: News tab with per-feed-type views (unfiltered / filtered / AI-filtered + raw sub-view)
- `GET /api/news/{feed}/export` and `POST /api/news/{feed}/import` endpoints for AI-filtered feeds (ADR-009)
- Export/Import UI controls (download button + file-upload) on AI-filtered feed views
- Read/unread tracking for `news_items` and `ai_filtered_views`; `keep_as_context` toggle for AI-filtered view rows
- Feed health alerting extended to all news feeds
- New DB tables: `news_items`, `filters`, `ai_filtered_views` (with `source_item_id` FK, denormalised `title`/`url`/`published_at`, `category` as plain text)
- `config.yaml`: `news_feeds` block with `type` and per-feed `filters` (no AI-specific config required)
- New dependency: `feedparser`
- Cron updated: `python src/cli/main.py && python src/cli/filter.py`

### Added — Enrichment
- `movies.imdb_id` column (VARCHAR 20, nullable): populated from OMDb `imdbID` field on enrichment; enables direct IMDb deep-links
- `migrate_001_schema.sh`: idempotent migration script covering all `ai_filtered_views` schema changes and `movies.imdb_id` addition

---

## v0.1.0 — M1–M4 (Movie Pipeline MVP)

### Added
- CLI ingester (`src/cli/main.py`): RSS fetching, parsing, deduplication, feed health tracking
- FastAPI web app (`src/webui/main.py`): JSON API + React frontend (CDN, no build step)
- Shared data layer (`src/common/`): SQLAlchemy models, DB setup, config loading
- On-demand rating enrichment via web UI (OMDb free tier)
- Read-tracking: mark/unmark movies as read, persisted to database
- Feed health alerting via local SMTP (triggers after 24h downtime)
- Configurable genre-specific filtering thresholds (`config.yaml`)
- Genre-priority ordering and year-section grouping in movie list
- MySQL primary + SQLite fallback database support

### Changed
- Project structure: `src/cli/` + `src/webui/` + `src/common/` (ADR-005; supersedes original `pelis/` package proposal)
- Invocation: two separate `python main.py` scripts instead of unified `pelis` CLI

### Security
- Web app binds to 127.0.0.1 only (not network-exposed)
- React JSX escaping prevents XSS from RSS feed data
- Config file stores secrets (file permissions: owner-only read, .gitignore'd)
