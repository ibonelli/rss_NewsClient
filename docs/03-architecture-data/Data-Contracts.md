# Data Contracts — pelis-feed

## 1) Entities

### Movie
- **Definition:** A movie entry discovered from the YTS RSS feed, potentially with multiple quality/resolution variants
- **Owner:** CLI Ingester (creates/updates); Web UI (reads, marks as read, triggers enrichment)

### Series
- **Definition:** One row per unique series title. Holds title-level metadata: `imdb_id` and the category flags `is_following` / `is_ignored`. Combined with a derived, non-stored check on the series' earliest-ingested episode, these produce one of four mutually-exclusive UI categories: Inbox (untriaged, earliest episode is S01E01, default), OnGoing (untriaged, earliest episode is not S01E01 — discovered mid-run), Following (`is_following=true`), Ignored (`is_ignored=true`, `is_following` always false in that case). See FR-088 for the exact Inbox/OnGoing rule.
- **Owner:** CLI Ingester (creates on first episode seen for title — sets `is_following=true` if the title matches a configured `series_feed.follow_filters` pattern, else Inbox/OnGoing default); Web UI (reads; sets/clears `is_following` and `is_ignored` via Follow/Unfollow/Ignore/Unignore actions)

### SeriesEpisode
- **Definition:** One row per unique `(series_id, season, episode)` combination. Holds episode-level data: quality variants, feed date, read status.
- **Owner:** CLI Ingester (creates/updates — merges quality variants); Web UI (reads; marks as read/unread)

### FeedHealth
- **Definition:** One row per configured feed tracking last success, last attempt, and error state. Used for downtime detection and alerting.
- **Owner:** CLI Ingester (writes); Web UI (reads); Alerter (reads for threshold check)

### NewsItem
- **Definition:** A raw news item fetched from any news feed type (unfiltered or filtered). All items are stored regardless of type.
- **Owner:** CLI Ingester (creates); CLI Filter Processor (updates `matched_filter_id`); Web UI (reads, marks as read)

### Filter
- **Definition:** A named regex pattern associated with a specific filtered feed. Synced from config on each Filter Processor run.
- **Owner:** CLI Filter Processor (syncs from config, applies regex); Web UI (reads for display)

### DesignItem
- **Definition:** An article fetched from a configurable design RSS feed. Stores title, summary, and image URL (if available in feed). No filtering — all items are stored and displayed.
- **Owner:** CLI Ingester (creates); Web UI (reads, marks as read/unread)

### AIFilteredView (legacy)
- **Definition:** Legacy table retained in DB schema; no longer written or read by the application (see Change-Log M10).
- **Owner:** None — application no longer writes or reads this table

## 2) Schema (SQLAlchemy Models)

### Movie

```python
class Movie(Base):
    __tablename__ = "movies"

    id: int                           # PK, auto-increment
    imdb_id: str | None               # nullable — OMDb imdbID e.g. "tt1234567"; populated on enrichment
    title: str                        # NOT NULL, max 500 chars
    year: int                         # NOT NULL, 4-digit year
    genres: str                       # NOT NULL, JSON array as text e.g. '["Action","Thriller"]'
    torrent_url: str                  # NOT NULL — not indexed directly (see torrent_url_hash)
    torrent_url_hash: str             # NOT NULL, UNIQUE, CHAR(64) — SHA-256(torrent_url); primary dedup key
    qualities: str                    # JSON array as text e.g. '[{"quality": "720p", "size": "850 MB"}, {"quality": "1080p", "size": "1.26 GB"}]' — size may be null if not parsed from the description
    imdb_rating: float | None         # 0.0–10.0, nullable (not yet enriched)
    rt_expert_rating: int | None      # 0–100, nullable
    rt_audience_rating: int | None    # 0–100, nullable
    poster_url: str | None            # nullable, URL to movie poster
    runtime: str | None               # nullable, raw runtime string as scraped e.g. "2hr 20 min" — format not normalized
    plot: str | None                  # nullable, full synopsis text (not truncated)
    feed_entry_date: datetime         # when the RSS entry was published
    enrichment_date: datetime | None  # when ratings were last fetched
    enrichment_error: str | None      # last enrichment error message, nullable
    is_read: bool                     # default False
    created_at: datetime              # auto-set on insert
    updated_at: datetime              # auto-set on insert and update
```

**Indexes:**
- `ux_movies_torrent_url_hash` UNIQUE on `torrent_url_hash` — primary dedup key (see "URL hash unique keys" below)
- `ix_movies_title_year` on `(title, year)` — secondary dedup lookup
- `ix_movies_year` on `year` — year-section queries
- `ix_movies_is_read` on `is_read` — filter out read movies

---

### Series

```python
class Series(Base):
    __tablename__ = "series"

    id: int              # PK, auto-increment
    title: str           # NOT NULL, UNIQUE — normalized series name
    imdb_id: str | None  # nullable — e.g. "tt0903747"; not in EZTV feed, reserved for future use
    is_following: bool   # default False — set true manually (Follow) or at creation by a follow_filters match
    is_ignored: bool     # default False — true = Ignored view only; MUST imply is_following=False when true
    created_at: datetime
    updated_at: datetime
```

Category is derived, not stored directly. Two flags plus one computed check on `series_episodes` produce four mutually-exclusive categories:
- **Following** = `is_following=True and is_ignored=False`
- **Ignored** = `is_ignored=True`
- **Inbox** = `is_following=False and is_ignored=False` AND the series' earliest-ingested episode (lowest `id`/earliest `created_at` in `series_episodes` for that `series_id`, skipping `season=0` specials) is `(season=1, episode=1)`
- **OnGoing** = `is_following=False and is_ignored=False` AND that earliest episode is NOT `(season=1, episode=1)`

The app enforces mutual exclusivity — setting `is_ignored=True` always clears `is_following`; `is_following` can only be set from Inbox or OnGoing. The Inbox/OnGoing split (FR-088) is computed at query time on every request, never written to a column — same pattern as the Movie Flagged/Un-Flagged split (FR-056).

**Indexes:**
- `ix_series_title` UNIQUE on `title` — primary dedup key
- `ix_series_is_ignored` on `is_ignored` — view filtering
- `ix_series_is_following` on `is_following` — view filtering

---

### SeriesEpisode

```python
class SeriesEpisode(Base):
    __tablename__ = "series_episodes"

    id: int                          # PK, auto-increment
    series_id: int                   # NOT NULL, FK → series.id
    season: int                      # NOT NULL
    episode: int                     # NOT NULL
    qualities: str                   # NOT NULL, JSON array: [{"quality": "720p", "torrent_page_url": "..."}]
    feed_entry_date: datetime | None # publication date from RSS entry
    ingested_at: datetime            # auto-set on insert
    is_read: bool                    # default False
    created_at: datetime             # auto-set on insert
    updated_at: datetime             # auto-set on insert and update
```

**Indexes:**
- `ix_series_episodes_series_season_ep` UNIQUE on `(series_id, season, episode)` — primary dedup key
- `ix_series_episodes_series_id` on `series_id` — join queries
- `ix_series_episodes_is_read` on `is_read`

---

### FeedHealth

```python
class FeedHealth(Base):
    __tablename__ = "feed_health"

    id: int                           # PK, auto-increment
    feed_name: str                    # NOT NULL, UNIQUE — matches feed name in config
    last_success_at: datetime | None  # last successful fetch timestamp
    last_attempt_at: datetime | None  # last fetch attempt timestamp
    last_error: str | None            # error message from last failed attempt
    consecutive_failures: int         # reset to 0 on success
    alert_sent_at: datetime | None    # when the last downtime alert was sent
```

**Indexes:**
- `ix_feed_health_feed_name` UNIQUE on `feed_name`

One row per configured feed (movie feed + series feed + each news feed). Upserted by the Ingester on each run.

---

### NewsItem

```python
class NewsItem(Base):
    __tablename__ = "news_items"

    id: int                         # PK, auto-increment
    feed_name: str                  # NOT NULL — matches feed name in config
    title: str                      # NOT NULL
    url: str                        # NOT NULL — not indexed directly (see url_hash)
    url_hash: str                   # NOT NULL, CHAR(64) — SHA-256(url); unique per feed with feed_name
    published_at: datetime | None   # publication date from feed (nullable if absent)
    full_content: str               # NOT NULL, full article text from feed — LONGTEXT on MySQL (TEXT caps at 65,535 bytes; some feeds provide the full article as raw HTML via <content>, which can exceed that), plain TEXT elsewhere (unbounded on SQLite)
    ingested_at: datetime           # auto-set on insert
    is_read: bool                   # default False — used by unfiltered and filtered feeds
    matched_filter_id: int | None   # FK → filters.id, nullable; set by Filter Processor for filtered feeds
```

**Indexes:**
- `ix_news_items_url_hash_feed` UNIQUE on `(url_hash, feed_name)` — dedup key (see "URL hash unique keys" below)
- `ix_news_items_feed_name` on `feed_name` — feed-scoped queries
- `ix_news_items_is_read` on `is_read`
- `ix_news_items_matched_filter_id` on `matched_filter_id`

---

### Filter

```python
class Filter(Base):
    __tablename__ = "filters"

    id: int          # PK, auto-increment
    feed_name: str   # NOT NULL — matches feed name in config
    name: str        # NOT NULL — human-readable label e.g. "vulnerabilities"
    pattern: str     # NOT NULL — regex string e.g. "(CVE|vulnerability|exploit)"
    created_at: datetime
```

**Indexes:**
- `ix_filters_feed_name_name` UNIQUE on `(feed_name, name)` — sync upsert key

Synced from config on each Filter Processor run. Rows not present in config are left in place (not deleted) to preserve FK references from `news_items` that were previously matched.

---

### DesignItem

```python
class DesignItem(Base):
    __tablename__ = "design_items"

    id: int                         # PK, auto-increment
    feed_name: str                  # NOT NULL — matches feed name in config
    title: str                      # NOT NULL
    url: str                        # NOT NULL — not indexed directly (see url_hash)
    url_hash: str                   # NOT NULL, CHAR(64) — SHA-256(url); unique per feed with feed_name
    published_at: datetime | None   # publication date from feed (nullable if absent)
    summary: str                    # NOT NULL, plain text (HTML stripped)
    image_url: str | None           # nullable — extracted best-effort from RSS (FR-063)
    ingested_at: datetime           # auto-set on insert
    is_read: bool                   # default False
```

**Indexes:**
- `ix_design_items_url_hash_feed` UNIQUE on `(url_hash, feed_name)` — dedup key (see "URL hash unique keys" below)
- `ix_design_items_feed_name` on `feed_name` — feed-scoped queries
- `ix_design_items_is_read` on `is_read`

---

### AIFilteredView (legacy — table retained, not used)

The `ai_filtered_views` table remains in the database schema but is no longer written or queried by the application. It is retained to avoid a destructive migration on existing installations.

### URL hash unique keys

`Movie.torrent_url` (`VARCHAR(1000)`), `NewsItem.url` and `DesignItem.url`
(`VARCHAR(2000)`) are never indexed directly. Under `utf8mb4` (4 bytes/char),
a unique index on any of them would exceed InnoDB's 3072-byte single-key-part
limit (`torrent_url`: 4000 bytes; `(url, feed_name)`: up to 9020 bytes) and
`CREATE TABLE` fails outright on MySQL. Instead, each table stores a
`*_hash` column — `hash_url()` in `src/common/models.py`, a SHA-256 hex
digest (`CHAR(64)` = 256 bytes under utf8mb4) — and the unique constraint is
on the hash (`torrent_url_hash` alone for `Movie`; `(url_hash, feed_name)`
for `NewsItem`/`DesignItem`, preserving the original per-feed dedup
semantics). The raw URL column is retained, unindexed, purely for
storage/display/linking. See `tools/migrate_006_url_hash_unique_keys.sh` for
the migration on an existing database.

## 3) Validation Rules

### Movie (on ingestion)
- **V-001:** `title` MUST NOT be empty or whitespace-only
- **V-002:** `year` MUST be a 4-digit integer between 1900 and current year + 1
- **V-003:** `genres` MUST be a valid JSON array with at least one non-empty string
- **V-004:** `torrent_url` MUST be a non-empty string
- **V-005:** `qualities` MUST be a valid JSON array of `{quality, size}` objects (`size` is optional/nullable); validation is intentionally loose — it only checks that the value is a list, not the shape of each element

### Movie (on enrichment)
- **V-006:** `imdb_rating`, if present, MUST be between 0.0 and 10.0
- **V-007:** `rt_expert_rating`, if present, MUST be between 0 and 100
- **V-008:** `rt_audience_rating`, if present, MUST be between 0 and 100

### Movie deduplication
- **V-009:** On insert, check for existing record with same `torrent_url` (via `torrent_url_hash`, see "URL hash unique keys")
- **V-010:** If match found, merge `qualities` arrays (union of available qualities, keyed by `quality` — matching entries keep their original `size`)
- **V-011:** If no URL match but same `title` + `year`, treat as same movie — merge qualities

`runtime` and `plot` are unconstrained optional metadata — parsed best-effort from the description, never rejected/validated, and not subject to any V-rule.

### Series (on ingestion)
- **V-021:** `title` MUST NOT be empty after normalization (stripping dots/underscores/dashes)
- **V-022:** `season` MUST be a non-negative integer (0 allowed for specials)
- **V-023:** `episode` MUST be a non-negative integer
- **V-024:** `qualities` MUST be a valid JSON array of objects each with non-empty `quality` and `torrent_page_url` fields
- **V-026:** `imdb_id`, if present, MUST match format `tt\d+`; store as-is, do not validate against external source
- **V-027:** Entries where S##E## cannot be parsed from the title MUST be logged and skipped (not stored)

### Series deduplication (two-level)
- **V-025a:** On insert, check `series` table for existing row with same `title`. If not found, insert a new `series` row (inheriting no `is_ignored` — defaults to `false`).
- **V-025b:** Check `series_episodes` table for existing row with same `(series_id, season, episode)`. If found, merge quality variants (union by `quality` value, preserving all `torrent_page_url` entries). If not found, insert a new `series_episodes` row.

### NewsItem (on ingestion)
- **V-012:** `title` MUST NOT be empty
- **V-013:** `url` MUST be a non-empty string
- **V-014:** `feed_name` MUST match a configured feed name in config
- **V-015:** Duplicate `(url, feed_name)` MUST be skipped (idempotent ingestion)

### DesignItem (on ingestion)
- **V-028:** `title` MUST NOT be empty
- **V-029:** `url` MUST be a non-empty string
- **V-030:** `feed_name` MUST match a configured feed name under `design_feeds:` in config
- **V-031:** Duplicate `(url, feed_name)` MUST be skipped (idempotent ingestion)
- **V-032:** `image_url`, if extracted, MUST be a non-empty string starting with `http`; otherwise stored as null
- **V-033:** `summary` is stored as plain text — HTML tags from `<description>` MUST be stripped before storage. If the feed provides no summary/description, store an empty string.

~~### AIFilteredView (on import) — Removed~~
~~V-016 through V-020 are no longer applicable — the import endpoint has been removed.~~

## 4) Compatibility Rules

- **Backward compatibility:** Not applicable (single-user, no API consumers)
- **Schema evolution:** SQLAlchemy `create_all()` adds new tables; manual `ALTER TABLE` for column additions. No formal migration framework.
- **Data formats:** `genres`, `qualities`, `tags` stored as JSON text for SQLite compatibility

## 5) Configuration Schema (YAML)

```yaml
database:
  url: "mysql+pymysql://user:pass@localhost/pelis_feed"
  # Alternative: "sqlite:///./pelis_feed.db"

feed:
  url: "https://yts.ag/rss"
  poll_interval_hours: 2

series_feed:
  url: "https://eztv.re/ezrss.xml"
  follow_filters:                          # optional — same {name, pattern} shape as news_feeds[].filters
    - name: "prestige-drama"
      pattern: "(Breaking Bad|Better Call Saul)"

alerting:
  smtp_host: "localhost"
  smtp_port: 25
  from_address: "pelis-feed@localhost"
  to_address: "user@localhost"
  downtime_threshold_hours: 24

enrichment:
  source: "omdb"    # or "tmdb", "imdbapi"
  api_key: ""
  timeout_seconds: 10

filtering:
  default:
    min_imdb: 6.0
    min_rt_expert: 60
    min_rt_audience: 50
  genres:
    action:
      min_imdb: 5.5
    romantic_comedy:
      min_imdb: 5.0
    documentary:
      min_imdb: 7.0
      min_rt_expert: 80
  older_movies:
    min_imdb: 7.5
    min_rt_expert: 75
    year_threshold: 6

genre_priority:
  - action
  - romantic_comedy
  - thriller
  - sci-fi
  - drama
  - horror
  - comedy
  - documentary

news_feeds:
  - name: "Tech News"
    url: "https://example.com/tech/feed"
    type: unfiltered

  - name: "Security"
    url: "https://example.com/security/feed"
    type: filtered
    filters:
      - name: "vulnerabilities"
        pattern: "(CVE|vulnerability|exploit|breach)"
      - name: "tooling"
        pattern: "(release|update|patch) v?[0-9]"

design_feeds:
  - name: "Designboom"
    url: "https://www.designboom.com/feed/"

  # - name: "Dezeen"
  #   url: "https://www.dezeen.com/feed/"

webapp:
  host: "127.0.0.1"
  port: 8080
```

## 6) Export JSON Contract (FR-033)

### Export — `GET /api/news/{feed_name}/export`

Available for any news feed type. Returns a JSON file download (`Content-Disposition: attachment`) containing all unread `news_items` for the feed.

```json
{
  "feed_name": "Tech News",
  "exported_at": "2026-06-19T10:00:00Z",
  "unread_items": [
    {
      "id": 517,
      "title": "Critical OpenSSL CVE patched in 3.4.1",
      "url": "https://openssl.org/news/...",
      "published_at": "2026-06-14T09:00:00Z",
      "content": "Full article text — not truncated."
    }
  ]
}
```

**`unread_items`** — `news_items` rows where `is_read = false` for this feed, regardless of which Read/Unread toggle state is active in the UI. Fields: `id`, `title`, `url`, `published_at`, `content`.

Log: `"Feed <name> export: N unread items"` (NFR-006).

~~**Import (`POST /api/news/{feed_name}/import`) — Removed.** The import endpoint no longer exists.~~

## 7) RSS Feed Contract (External — Not Controlled)

**Movie feed:** `https://yts.ag/rss` — RSS 2.0 XML. Fields per `<item>`: `<title>`, `<link>`, `<pubDate>`, `<description>` (HTML blob with poster/genre/rating/size/runtime/plot), `<enclosure>` (torrent URL). Parser extracts title/year/quality from `<title>` via regex; genre/IMDb rating/poster/size/runtime/plot from `<description>` HTML. The description's real layout order is IMDB Rating → Genre → Size → Runtime → plot synopsis; genre/size/runtime are each bounded by their own regex (genre via a lookahead on the labels that can follow it, size/runtime via their own value shape) rather than a single shared terminator, since the description text is flattened to one line with no tag/line-break structure preserved.

**Series feed:** `https://eztv.re/ezrss.xml` — RSS 2.0 XML. Fields per `<item>`: `<title>` (series name + S##E## + quality, e.g. `Show Name S01E05 720p WEB` or `Show.Name.S01E05.720p.WEB`), `<link>` (torrent page URL), `<pubDate>`. No IMDb ID element is present in the feed — `series.imdb_id` is always stored as null; the UI falls back to an IMDb title-search URL (see ADR-010). Parser extracts series name/season/episode/quality via regex on `<title>`; torrent page URL from `<link>`. Entries with no S##E## pattern are skipped (V-027).

**News feeds:** RSS 2.0 or Atom 1.0 (parsed via feedparser). Fields used: title, link, published/updated, summary/content. Format varies by feed — feedparser normalises differences.

**Risk:** All feed formats are uncontrolled and may change without notice. Parser must log warnings on unexpected structure and skip unparseable items rather than crashing.

## 8) API Response Contracts (JSON)

### GET `/api/movies`

Query params:
- `read` (bool, default `false`) — `false` = unread movies; `true` = read movies
- `flagged` (bool, default `true`) — `true` = movies that pass the rating/genre filter ("Flagged"); `false` = movies that fail it ("Un-Flagged")

Default (`read=false&flagged=true`): unread movies that pass the filter — same behaviour as the original Filtered view.

Movies with no ratings (unenriched) always pass the filter and appear in the Flagged (`flagged=true`) results.
The Flagged/Un-Flagged split is computed at query time from config thresholds; no `is_flagged` column is stored in the DB.

```json
{
  "read": false,
  "flagged": true,
  "sections": [
    {
      "year": 2026,
      "label": "2026",
      "movies": [
        {
          "id": 42,
          "title": "Movie Name",
          "year": 2026,
          "genres": ["Action", "Thriller"],
          "qualities": [
            {"quality": "720p", "size": "850 MB"},
            {"quality": "1080p", "size": "1.26 GB"}
          ],
          "torrent_url": "https://...",
          "imdb_id": "tt1234567",
          "imdb_rating": 7.2,
          "rt_expert_rating": 85,
          "rt_audience_rating": 78,
          "poster_url": "https://...",
          "runtime": "2hr 20 min",
          "plot": "A meticulous jewel thief risks his flawless record...",
          "feed_entry_date": "2026-05-20T14:30:00Z",
          "enrichment_date": "2026-05-20T15:00:00Z",
          "enrichment_error": null,
          "is_read": false
        }
      ]
    },
    {
      "year": null,
      "label": "Older (pre-2021)",
      "movies": []
    }
  ],
  "total_count": 150
}
```

### POST `/api/movies/{id}/read` and `/api/movies/{id}/unread`

```json
{ "id": 42, "title": "Movie Name", "is_read": true, "updated_at": "2026-05-20T16:00:00Z" }
```

### POST `/api/movies/read-all`

Query params:
- `flagged` (bool, default `true`) — scopes which unread movies are marked read: `true` marks only Flagged (filter-passing) unread movies; `false` marks only Un-Flagged (filter-failing) unread movies

The Flagged/Un-Flagged split is computed at query time (same logic as `GET /api/movies`). Only unread (`is_read=false`) movies are ever affected.

```json
{ "marked_read": 30 }
```

### POST `/api/movies/{id}/enrich`

```json
{
  "id": 42,
  "title": "Movie Name",
  "imdb_id": "tt1234567",
  "imdb_rating": 7.2,
  "rt_expert_rating": 85,
  "rt_audience_rating": 78,
  "enrichment_date": "2026-05-20T16:10:00Z",
  "enrichment_error": null
}
```

On failure: same shape with all rating fields `null`, `imdb_id` `null`, and `enrichment_error` populated.

### GET `/api/series`

Query params:
- `read` (bool, default `false`) — `false` = episodes with `is_read=false` (Unread); `true` = episodes with `is_read=true` (Read)
- `category` (string enum, default `following`) — one of `inbox`, `ongoing`, `following`, `ignored`:
  - `following` → `is_following=true, is_ignored=false`
  - `ignored` → `is_ignored=true`
  - `inbox` → `is_following=false, is_ignored=false`, AND the series' earliest-ingested episode (skipping season-0 specials) is `(season=1, episode=1)`
  - `ongoing` → `is_following=false, is_ignored=false`, AND that earliest episode is NOT `(season=1, episode=1)` (FR-088)

A series title appears in the response only if it has at least one episode matching the `read` filter.

The Only-Title/Full view mode (FR-089) is a purely client-side rendering choice — it has no corresponding query param or response field. The client always receives the full `seasons`/`episodes` tree shown below and chooses whether to render it (Full) or collapse it to a title + count (Only Title, where the count is `len(episodes)` across all seasons in the response).

```json
{
  "read": false,
  "category": "following",
  "series": [
    {
      "id": 1,
      "title": "Breaking Bad",
      "imdb_id": null,
      "imdb_url": "https://www.imdb.com/search/title/?title=Breaking+Bad&title_type=tv_series",
      "is_following": true,
      "is_ignored": false,
      "seasons": [
        {
          "season": 1,
          "episodes": [
            {
              "id": 7,
              "episode": 1,
              "qualities": [
                {"quality": "720p", "torrent_page_url": "https://eztv.re/ep/..."},
                {"quality": "1080p", "torrent_page_url": "https://eztv.re/ep/..."}
              ],
              "feed_entry_date": "2026-06-19T10:00:00Z",
              "is_read": false
            }
          ]
        }
      ]
    }
  ]
}
```

`imdb_url` uses `https://www.imdb.com/title/{imdb_id}/` when `imdb_id` is known; falls back to an IMDb title-search URL otherwise (ADR-010). `is_following`/`is_ignored` live only at the series level — episodes carry no category flag of their own.

### POST `/api/series/{series_id}/follow`, `/unfollow`, `/ignore`, `/unignore`

All four set/clear `is_following` / `is_ignored` on the `series` row identified by `series_id` (PK), enforcing the mutual-exclusivity rule (a series is never both Following and Ignored):
- `follow` — `is_following=true` (only meaningful from Inbox; `is_ignored` is already false there)
- `unfollow` — `is_following=false` (returns the series to Inbox)
- `ignore` — `is_ignored=true` AND `is_following=false`
- `unignore` — `is_ignored=false` (returns the series to Inbox, not Following)

```json
{ "id": 1, "title": "Breaking Bad", "is_following": false, "is_ignored": true }
```

### POST `/api/series/episodes/{episode_id}/read` and `/api/series/episodes/{episode_id}/unread`

Sets `is_read` on a `series_episodes` row.

```json
{ "id": 7, "is_read": true }
```

### POST `/api/series/read-all`

Query params:
- `category` (string enum, default `following`) — one of `inbox`, `ongoing`, `following`, `ignored`; scopes which unread episodes are marked read to the given category only (see `GET /api/series` above)

Only `is_read=false` episodes within the scoped series are affected.

```json
{ "marked_read": 22 }
```

### GET `/api/health`

```json
{
  "feeds": [
    {
      "feed_name": "yts_movies",
      "last_success_at": "2026-06-16T14:00:00Z",
      "last_attempt_at": "2026-06-16T14:00:00Z",
      "last_error": null,
      "consecutive_failures": 0,
      "status": "healthy"
    },
    {
      "feed_name": "eztv_series",
      "last_success_at": "2026-06-16T14:01:00Z",
      "last_attempt_at": "2026-06-16T14:01:00Z",
      "last_error": null,
      "consecutive_failures": 0,
      "status": "healthy"
    },
    {
      "feed_name": "AI News",
      "last_success_at": "2026-06-16T13:58:00Z",
      "last_attempt_at": "2026-06-16T13:58:00Z",
      "last_error": null,
      "consecutive_failures": 0,
      "status": "healthy"
    }
  ]
}
```

`status` values: `"healthy"` (last success < 24h ago), `"degraded"` (≥ 24h), `"unknown"` (never fetched).

### GET `/api/news`

```json
{
  "feeds": [
    { "name": "Tech News", "type": "unfiltered", "unread_count": 12 },
    { "name": "Security", "type": "filtered", "unread_count": 3 }
  ]
}
```

### GET `/api/news/{feed_name}/items`

Query params:
- `read` (bool, default `false`) — `false` = unread items (`is_read=false`); `true` = read items (`is_read=true`)

Returns items appropriate to the feed type, filtered by read state:
- `unfiltered` → `news_items` for the feed matching `is_read`
- `filtered` → `news_items` where `matched_filter_id` is not null, matching `is_read`

```json
{
  "feed_name": "Security",
  "type": "filtered",
  "read": false,
  "items": [
    {
      "id": 517,
      "title": "Critical OpenSSL CVE patched in 3.4.1",
      "url": "https://openssl.org/news/...",
      "published_at": "2026-06-14T09:00:00Z",
      "is_read": false,
      "matched_filter_name": "vulnerabilities"
    }
  ]
}
```

For `filtered` type, each item includes `matched_filter_name`. For `unfiltered`, this field is absent.

~~**`GET /api/news/{feed_name}/raw` — Removed.**~~

### POST `/api/news/items/{id}/read` and `/api/news/items/{id}/unread`

```json
{ "id": 517, "is_read": true }
```

~~**`POST /api/news/views/{id}/read` and `/api/news/views/{id}/unread` — Removed.** The `ai_filtered` feed type has been eliminated.~~

~~**`POST /api/news/views/{id}/keep` and `/api/news/views/{id}/unkeep` — Removed.**~~

### POST `/api/news/{feed_name}/read-all`

Marks all unread `news_items` for the feed as read (`is_read = true`). Available for `unfiltered` and `filtered` feeds. Only called from the Unread toggle state.

```json
{ "ok": true }
```

### GET `/api/news/{feed_name}/export`

Available for any news feed type. Returns `Content-Disposition: attachment; filename="<feed_name>-export.json"`. Shape documented in Section 6. Always exports unread `news_items` regardless of the current UI toggle state.

~~**`POST /api/news/{feed_name}/import` — Removed.**~~

### GET `/api/design`

Returns all configured design feeds with unread counts.

```json
{
  "feeds": [
    { "name": "Designboom", "unread_count": 15 }
  ]
}
```

### GET `/api/design/{feed_name}/items`

Query params:
- `read` (bool, default `false`) — `false` = unread items (`is_read=false`); `true` = read items (`is_read=true`)

```json
{
  "feed_name": "Designboom",
  "read": false,
  "items": [
    {
      "id": 1,
      "title": "Studio Drift's kinetic installation at Design Miami",
      "url": "https://www.designboom.com/art/studio-drift-...",
      "published_at": "2026-06-29T10:00:00Z",
      "summary": "Dutch design studio Drift presents a new kinetic sculpture...",
      "image_url": "https://www.designboom.com/wp-content/uploads/...",
      "is_read": false
    }
  ]
}
```

`image_url` is `null` when no image was found in the feed entry (FR-063).

### POST `/api/design/items/{id}/read` and `/api/design/items/{id}/unread`

Sets `is_read` on a `design_items` row.

```json
{ "id": 1, "is_read": true }
```

### POST `/api/design/{feed_name}/read-all`

Marks all unread `design_items` for the feed as read. Only called from the Unread toggle state.

```json
{ "marked_read": 15 }
```

### Error Responses (All Endpoints)

```json
{ "detail": "Not found", "status_code": 404 }
```

Standard HTTP status codes: `200` success, `404` not found, `500` internal error.
