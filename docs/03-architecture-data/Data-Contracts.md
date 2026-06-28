# Data Contracts — pelis-feed

## 1) Entities

### Movie
- **Definition:** A movie entry discovered from the YTS RSS feed, potentially with multiple quality/resolution variants
- **Owner:** CLI Ingester (creates/updates); Web UI (reads, marks as read, triggers enrichment)

### Series
- **Definition:** One row per unique series title. Holds title-level metadata: `imdb_id` and the `is_ignored` flag.
- **Owner:** CLI Ingester (creates on first episode seen for title); Web UI (reads; sets `is_ignored`)

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
    torrent_url: str                  # NOT NULL, UNIQUE — primary dedup key
    qualities: str                    # JSON array as text e.g. '["720p","1080p"]'
    imdb_rating: float | None         # 0.0–10.0, nullable (not yet enriched)
    rt_expert_rating: int | None      # 0–100, nullable
    rt_audience_rating: int | None    # 0–100, nullable
    poster_url: str | None            # nullable, URL to movie poster
    feed_entry_date: datetime         # when the RSS entry was published
    enrichment_date: datetime | None  # when ratings were last fetched
    enrichment_error: str | None      # last enrichment error message, nullable
    is_read: bool                     # default False
    created_at: datetime              # auto-set on insert
    updated_at: datetime              # auto-set on insert and update
```

**Indexes:**
- `ix_movies_torrent_url` UNIQUE on `torrent_url` — primary dedup key
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
    is_ignored: bool     # default False — series appears in Not-Ignored view; true = Ignored view only
    created_at: datetime
    updated_at: datetime
```

**Indexes:**
- `ix_series_title` UNIQUE on `title` — primary dedup key
- `ix_series_is_ignored` on `is_ignored` — view filtering

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
    url: str                        # NOT NULL, UNIQUE per feed — dedup key
    published_at: datetime | None   # publication date from feed (nullable if absent)
    full_content: str               # NOT NULL, full article text from feed
    ingested_at: datetime           # auto-set on insert
    is_read: bool                   # default False — used by unfiltered and filtered feeds
    matched_filter_id: int | None   # FK → filters.id, nullable; set by Filter Processor for filtered feeds
```

**Indexes:**
- `ix_news_items_url_feed` UNIQUE on `(url, feed_name)` — dedup key
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

### AIFilteredView (legacy — table retained, not used)

The `ai_filtered_views` table remains in the database schema but is no longer written or queried by the application. It is retained to avoid a destructive migration on existing installations.

## 3) Validation Rules

### Movie (on ingestion)
- **V-001:** `title` MUST NOT be empty or whitespace-only
- **V-002:** `year` MUST be a 4-digit integer between 1900 and current year + 1
- **V-003:** `genres` MUST be a valid JSON array with at least one non-empty string
- **V-004:** `torrent_url` MUST be a non-empty string
- **V-005:** `qualities` MUST be a valid JSON array

### Movie (on enrichment)
- **V-006:** `imdb_rating`, if present, MUST be between 0.0 and 10.0
- **V-007:** `rt_expert_rating`, if present, MUST be between 0 and 100
- **V-008:** `rt_audience_rating`, if present, MUST be between 0 and 100

### Movie deduplication
- **V-009:** On insert, check for existing record with same `torrent_url`
- **V-010:** If match found, merge `qualities` arrays (union of available qualities)
- **V-011:** If no URL match but same `title` + `year`, treat as same movie — merge qualities

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

**Movie feed:** `https://yts.ag/rss` — RSS 2.0 XML. Fields per `<item>`: `<title>`, `<link>`, `<pubDate>`, `<description>` (HTML blob with poster/genre/rating), `<enclosure>` (torrent URL). Parser extracts title/year/quality from `<title>` via regex; genre/IMDb/poster from `<description>` HTML.

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
          "qualities": ["720p", "1080p"],
          "torrent_url": "https://...",
          "imdb_id": "tt1234567",
          "imdb_rating": 7.2,
          "rt_expert_rating": 85,
          "rt_audience_rating": 78,
          "poster_url": "https://...",
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
- `ignored` (bool, default `false`) — `false` = non-ignored series (Not-Ignored); `true` = ignored series

A series title appears in the response only if it has at least one episode matching the `read` filter.

```json
{
  "read": false,
  "ignored": false,
  "series": [
    {
      "id": 1,
      "title": "Breaking Bad",
      "imdb_id": null,
      "imdb_url": "https://www.imdb.com/search/title/?title=Breaking+Bad&title_type=tv_series",
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

`imdb_url` uses `https://www.imdb.com/title/{imdb_id}/` when `imdb_id` is known; falls back to an IMDb title-search URL otherwise (ADR-010). `is_ignored` lives only at the series level — episodes carry no ignore flag.

### POST `/api/series/{series_id}/ignore` and `/api/series/{series_id}/unignore`

Sets `is_ignored` on the `series` row identified by `series_id` (PK). Ignored series appear only when `ignored=true` is passed to `GET /api/series`.

```json
{ "id": 1, "title": "Breaking Bad", "is_ignored": true }
```

### POST `/api/series/episodes/{episode_id}/read` and `/api/series/episodes/{episode_id}/unread`

Sets `is_read` on a `series_episodes` row.

```json
{ "id": 7, "is_read": true }
```

### POST `/api/series/read-all`

Query params:
- `ignored` (bool, default `false`) — scopes which unread episodes are marked read: `false` marks only episodes of non-ignored series; `true` marks only episodes of ignored series

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

### Error Responses (All Endpoints)

```json
{ "detail": "Not found", "status_code": 404 }
```

Standard HTTP status codes: `200` success, `404` not found, `500` internal error.
