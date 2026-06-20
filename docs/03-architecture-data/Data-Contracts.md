# Data Contracts — pelis-feed

## 1) Entities

### Movie
- **Definition:** A movie entry discovered from the YTS RSS feed, potentially with multiple quality/resolution variants
- **Owner:** CLI Ingester (creates/updates); Web UI (reads, marks as read, triggers enrichment)

### Series
- **Definition:** A TV series episode entry from the EZTV RSS feed. One row per unique `(title, season, episode)` combination; quality variants are merged into the `qualities` JSON array on the same row.
- **Owner:** CLI Ingester (creates/updates); Web UI (reads, marks as read)

### FeedHealth
- **Definition:** One row per configured feed tracking last success, last attempt, and error state. Used for downtime detection and alerting.
- **Owner:** CLI Ingester (writes); Web UI (reads); Alerter (reads for threshold check)

### NewsItem
- **Definition:** A raw news item fetched from any news feed type (unfiltered, filtered, or AI-filtered). All items are stored regardless of type.
- **Owner:** CLI Ingester (creates); CLI Filter Processor (updates `matched_filter_id`); Web UI (reads, marks as read)

### Filter
- **Definition:** A named regex pattern associated with a specific filtered feed. Synced from config on each Filter Processor run.
- **Owner:** CLI Filter Processor (syncs from config, applies regex); Web UI (reads for display)

### AIFilteredView
- **Definition:** An AI-processed result for a news item, imported by the user after external processing. One row per surfaced news item. The full set for a feed is replaced on each import. Absence means the item has not been surfaced by any import yet.
- **Owner:** Web UI (creates/replaces on import; reads; marks as read; sets keep_as_context)

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

    id: int                          # PK, auto-increment
    title: str                       # NOT NULL — normalized series name
    imdb_id: str | None              # nullable — e.g. "tt0903747"; from RSS entry
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
- `ix_series_title_season_episode` UNIQUE on `(title, season, episode)` — primary dedup key
- `ix_series_title` on `title` — grouping queries
- `ix_series_is_read` on `is_read`

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

### AIFilteredView

```python
class AIFilteredView(Base):
    __tablename__ = "ai_filtered_views"

    id: int                       # PK, auto-increment
    source_item_id: int           # NOT NULL, FK → news_items.id
    feed_name: str                # NOT NULL — denormalized for query convenience
    title: str                    # NOT NULL — denormalized from import payload
    url: str                      # NOT NULL — denormalized from import payload
    published_at: datetime | None # nullable — from import payload
    category: str | None          # free-form label assigned by external AI, nullable
    summary: str | None           # 1–2 sentence AI-generated summary, nullable
    tags: str | None              # JSON array as text e.g. '["CVE","patch"]', nullable
    is_read: bool                 # default False — user-controlled; NOT reset on import
    keep_as_context: bool         # default False — user-controlled; if True, included in next export
    ingested_at: datetime         # when this row was written by the import
```

**Indexes:**
- `ix_ai_filtered_views_source_item_id` UNIQUE on `source_item_id` — one row per news item
- `ix_ai_filtered_views_feed_name` on `feed_name`
- `ix_ai_filtered_views_is_read` on `is_read`
- `ix_ai_filtered_views_keep_as_context` on `keep_as_context` — export context query

**Import behaviour:** On `POST /api/news/{feed}/import`, all existing rows for that feed are deleted and replaced with the payload rows. `is_read` and `keep_as_context` are NOT preserved from deleted rows — they reset to `false` on each import. (The export captures `keep_as_context` items before replacement so the external tool can re-include them.)

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

### Series deduplication
- **V-025:** On insert, check for existing record with same `(title, season, episode)`; if found, merge quality variants (union by `quality` value, preserving all `torrent_page_url` entries)

### NewsItem (on ingestion)
- **V-012:** `title` MUST NOT be empty
- **V-013:** `url` MUST be a non-empty string
- **V-014:** `feed_name` MUST match a configured feed name in config
- **V-015:** Duplicate `(url, feed_name)` MUST be skipped (idempotent ingestion)

### AIFilteredView (on import)
- **V-016:** `source_item_id` in import payload MUST match a `news_items.id` belonging to the target feed; discard row if not found
- **V-017:** `category` string, if present, MUST be non-empty (1–50 chars); skip row if blank
- **V-018:** `summary` MUST be a non-empty string if present
- **V-019:** `tags` MUST be a valid JSON array of non-empty strings if present
- **V-020:** `title` and `url` MUST be non-empty strings; reject entire import if any row is missing them

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

  - name: "AI News"
    url: "https://example.com/ai/feed"
    type: ai_filtered

webapp:
  host: "127.0.0.1"
  port: 8080
```

## 6) Export / Import JSON Contract (FR-033, FR-034)

### Export — `GET /api/news/{feed_name}/export`

Returns a JSON file download. The external AI tool reads this file, processes it, and produces the import payload.

```json
{
  "feed_name": "AI News",
  "exported_at": "2026-06-19T10:00:00Z",
  "unread_items": [
    {
      "id": 517,
      "title": "Critical OpenSSL CVE patched in 3.4.1",
      "url": "https://openssl.org/news/...",
      "published_at": "2026-06-14T09:00:00Z",
      "content": "Full article text — not truncated."
    }
  ],
  "context_items": [
    {
      "source_item_id": 412,
      "title": "Log4Shell follow-up: affected projects list updated",
      "url": "https://example.com/log4shell-update",
      "published_at": "2026-06-10T08:00:00Z",
      "category": "Security",
      "summary": "The affected projects list for Log4Shell was updated with 12 new entries.",
      "tags": ["Log4Shell", "CVE", "Java"]
    }
  ]
}
```

**`unread_items`** — `news_items` rows where `is_read = false` for this feed. Fields: `id`, `title`, `url`, `published_at`, `content`. The `id` is the `news_items.id` that the import must reference as `source_item_id`.

**`context_items`** — `ai_filtered_views` rows where `keep_as_context = true` for this feed. Included for the external tool to use as context/examples; the tool is not expected to return them in its output.

Log: `"Feed <name> export: N unread items, M context items"` (NFR-006).

---

### Import — `POST /api/news/{feed_name}/import`

The external AI tool produces this payload. The user uploads it via the web UI.

```json
{
  "views": [
    {
      "source_item_id": 517,
      "title": "Critical OpenSSL CVE patched in 3.4.1",
      "url": "https://openssl.org/news/...",
      "published_at": "2026-06-14T09:00:00Z",
      "category": "Security Vulnerability",
      "summary": "A critical OpenSSL CVE was patched in 3.4.1; all users should upgrade immediately.",
      "tags": ["CVE", "OpenSSL", "patch"]
    }
  ]
}
```

**Import field contract:**

| Field | Type | Rules |
|---|---|---|
| `source_item_id` | int | MUST match a `news_items.id` for this feed (V-016); discard row if not found |
| `title` | string | MUST be non-empty (V-020) |
| `url` | string | MUST be non-empty (V-020) |
| `published_at` | string (ISO 8601) | nullable |
| `category` | string | Optional; 1–50 chars if present (V-017) |
| `summary` | string | Optional; non-empty if present (V-018) |
| `tags` | string[] | Optional; array of non-empty strings if present (V-019) |

**Import flow:**

```
1. Validate feed exists and is ai_filtered type — 404 if not
2. Validate payload is valid JSON with a "views" array — 400 if not
3. For each row: validate source_item_id, title, url — discard invalid rows and log (V-016, V-020)
4. DELETE all existing ai_filtered_views rows for this feed
5. INSERT valid rows with ingested_at = now(); is_read = false; keep_as_context = false
6. Return: { "imported": N, "discarded": M }

log: "Feed <name> import: received N rows, persisted P, discarded D" (NFR-006)
```

**Error handling:**

| Failure | HTTP response |
|---|---|
| Feed not found or not `ai_filtered` type | `404 Not Found` |
| Payload is not valid JSON | `400 Bad Request` |
| Individual row fails validation (V-016, V-020) | Row discarded, logged; remainder processed; `200` with discard count |

## 7) RSS Feed Contract (External — Not Controlled)

**Movie feed:** `https://yts.ag/rss` — RSS 2.0 XML. Fields per `<item>`: `<title>`, `<link>`, `<pubDate>`, `<description>` (HTML blob with poster/genre/rating), `<enclosure>` (torrent URL). Parser extracts title/year/quality from `<title>` via regex; genre/IMDb/poster from `<description>` HTML.

**Series feed:** `https://eztv.re/ezrss.xml` — RSS 2.0 XML. Fields per `<item>`: `<title>` (contains series name + SxxExx + quality, e.g. `Show.Name.S01E05.720p.WEB`), `<link>` (torrent page URL), `<pubDate>`, and an EZTV-specific `<torrent:magnetURI>` and `<imdb>` or similar element for the IMDb ID. Parser extracts series name/season/episode/quality via regex on `<title>`; torrent page URL from `<link>`; IMDb ID from feed-specific element. Exact structure requires live feed inspection before finalising parser (Q-009).

**News feeds:** RSS 2.0 or Atom 1.0 (parsed via feedparser). Fields used: title, link, published/updated, summary/content. Format varies by feed — feedparser normalises differences.

**Risk:** All feed formats are uncontrolled and may change without notice. Parser must log warnings on unexpected structure and skip unparseable items rather than crashing.

## 8) API Response Contracts (JSON)

### GET `/api/movies`

Query params:
- `filtered` (bool, default `true`) — when `false`, rating/genre filters are skipped and all unread movies are returned

```json
{
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

```json
{
  "series": [
    {
      "title": "Breaking Bad",
      "imdb_id": "tt0903747",
      "imdb_url": "https://www.imdb.com/title/tt0903747/",
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

`imdb_url` is omitted from the response when `imdb_id` is null.

### POST `/api/series/{id}/read` and `/api/series/{id}/unread`

```json
{ "id": 7, "is_read": true }
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
    { "name": "Security", "type": "filtered", "unread_count": 3 },
    { "name": "AI News", "type": "ai_filtered", "unread_count": 7 }
  ]
}
```

### GET `/api/news/{feed_name}/items`

Returns items appropriate to the feed type:
- `unfiltered` → all `news_items` for the feed
- `filtered` → only `news_items` where `matched_filter_id` is not null (includes filter name)
- `ai_filtered` → rows from `ai_filtered_views` for the feed

```json
{
  "feed_name": "AI News",
  "type": "ai_filtered",
  "items": [
    {
      "id": 88,
      "source_item_id": 517,
      "title": "Critical OpenSSL CVE patched in 3.4.1",
      "url": "https://openssl.org/news/...",
      "published_at": "2026-06-14T09:00:00Z",
      "category": "Security Vulnerability",
      "summary": "A critical OpenSSL CVE was patched in 3.4.1; upgrade immediately.",
      "tags": ["CVE", "OpenSSL", "patch"],
      "is_read": false,
      "keep_as_context": false,
      "ingested_at": "2026-06-19T10:05:00Z"
    }
  ]
}
```

For `filtered` type, each item also includes `matched_filter_name: "vulnerabilities"`.

### GET `/api/news/{feed_name}/raw`

Only valid for `ai_filtered` feeds (FR-032). Returns the raw `news_items` rows so the user can browse unprocessed items.

```json
{
  "feed_name": "AI News",
  "items": [
    {
      "id": 517,
      "title": "Critical OpenSSL CVE patched in 3.4.1",
      "url": "https://openssl.org/news/...",
      "published_at": "2026-06-14T09:00:00Z",
      "full_content": "Full article text...",
      "ingested_at": "2026-06-14T10:00:00Z",
      "is_read": false,
      "matched_filter_id": null,
      "has_ai_view": true
    }
  ]
}
```

`has_ai_view` indicates whether an `ai_filtered_views` row exists for this item (useful for UI to distinguish processed vs. pending items).

### POST `/api/news/items/{id}/read` and `/api/news/items/{id}/unread`

```json
{ "id": 517, "is_read": true }
```

### POST `/api/news/views/{id}/read` and `/api/news/views/{id}/unread`

```json
{ "id": 88, "is_read": true }
```

### POST `/api/news/views/{id}/keep` and `/api/news/views/{id}/unkeep`

```json
{ "id": 88, "keep_as_context": true }
```

### GET `/api/news/{feed_name}/export`

Returns `Content-Disposition: attachment; filename="<feed_name>-export.json"`. Shape documented in Section 6.

### POST `/api/news/{feed_name}/import`

```json
{ "imported": 12, "discarded": 1 }
```

On error: `400` with `{ "detail": "..." }`.

### Error Responses (All Endpoints)

```json
{ "detail": "Not found", "status_code": 404 }
```

Standard HTTP status codes: `200` success, `404` not found, `500` internal error.
