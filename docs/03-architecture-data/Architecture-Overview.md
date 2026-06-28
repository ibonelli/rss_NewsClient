# Architecture Overview — pelis-feed

## 1) Boundaries & Ownership

| Component | Responsibility | Runtime |
|---|---|---|
| **CLI Ingester** (`src/cli/main.py`) | Fetch all RSS/Atom feeds (movie + series + news), parse, deduplicate (movies and series), store raw data to `movies`, `series`, `series_episodes`, and `news_items`, update feed health | Cron-triggered process (runs and exits, step 1) |
| **CLI Filter Processor** (`src/cli/filter.py`) | Sync `filters` table from config; for each `filtered` feed, regex-match `news_items` and set `matched_filter_id` on matches — never deletes rows | Cron-triggered process (runs and exits, step 2 — immediately after Ingester) |
| **FastAPI Web UI** (`src/webui/main.py`) | JSON API for movies, series, and news (filtering, read-tracking, on-demand enrichment); AI-filtered export (`GET`) and import (`POST`) endpoints; static React frontend | Long-running local process (on-demand) |
| **Database** (MySQL/SQLite) | Persistent state for all data | Shared resource |
| **Config file** (`config.yaml`) | Feed definitions, filter patterns, rating thresholds, connection strings | Shared resource (read by both processes) |
| **External AI Tool** | Consumes export JSON, produces import JSON; operated entirely outside this application | External (user-operated) |

### Project Structure

```
src/
├── cli/
│   ├── main.py         # Ingester entry point (movies, series, and news)
│   ├── filter.py       # Filter Processor entry point (regex flagging only)
│   ├── fetcher.py      # RSS/Atom fetch + parse (movies, series via EZTV, and news)
│   ├── dedup.py        # Movie and series deduplication logic
│   └── alerter.py      # Feed health check + SMTP alert
├── webui/
│   ├── main.py         # Uvicorn entry point
│   ├── app.py          # FastAPI app factory + static file mounting
│   ├── routes.py       # JSON API route handlers (movies, series, news)
│   ├── filters.py      # Movie filtering + sorting logic
│   ├── enrichment.py   # On-demand OMDb/TMDb enrichment
│   └── static/
│       ├── index.html  # HTML shell (loads React via CDN)
│       ├── app.js      # React components (JSX via Babel CDN)
│       └── styles.css
└── common/
    ├── models.py       # SQLAlchemy models (all tables, shared)
    ├── db.py           # Engine/session factory, init_db()
    └── config.py       # YAML config loading + validation
```

## 2) Interfaces

### Cron Entry Points

| Command | Description | Schedule |
|---|---|---|
| `python src/cli/main.py` | Fetch all feeds (movies, series, news), store raw data, update feed health | Every ~2h (cron step 1) |
| `python src/cli/filter.py` | Sync filters from config; regex-flag `news_items` for `filtered` feeds | Every ~2h (cron step 2, immediately after step 1) |
| `python src/webui/main.py` | Start FastAPI web app (Uvicorn) | Manual, on-demand |

**Cron entry:** `0 */2 * * * /path/to/venv/bin/python /path/to/src/cli/main.py && /path/to/venv/bin/python /path/to/src/cli/filter.py`

### Web App Routes (FastAPI — JSON API)

**Movies**

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serve static React frontend (`index.html`) |
| GET | `/api/movies` | Movie list grouped by year; `view` param: `filtered` (default) \| `non_filtered` \| `read_filtered` \| `read_non_filtered` |
| POST | `/api/movies/{id}/read` | Mark movie as read |
| POST | `/api/movies/{id}/unread` | Mark movie as unread |
| POST | `/api/movies/{id}/enrich` | Trigger on-demand rating enrichment |
| GET | `/api/health` | Feed health status for all feeds |
| GET | `/static/*` | Static assets (JS, CSS) |

**Series**

| Method | Path | Description |
|---|---|---|
| GET | `/api/series` | Series grouped by title → season → episode; `view` param: `unread` (default) \| `all` \| `ignored` |
| POST | `/api/series/{series_id}/ignore` | Set `is_ignored = true` on `series` row |
| POST | `/api/series/{series_id}/unignore` | Set `is_ignored = false` on `series` row |
| POST | `/api/series/episodes/{episode_id}/read` | Mark episode as read |
| POST | `/api/series/episodes/{episode_id}/unread` | Mark episode as unread |
| POST | `/api/series/read-all` | Mark all unread episodes as read |

**News**

| Method | Path | Description |
|---|---|---|
| GET | `/api/news` | All news feeds with metadata and item counts |
| GET | `/api/news/{feed_name}/items` | Items for a feed (filtered/AI-filtered/unfiltered per feed type) |
| GET | `/api/news/{feed_name}/raw` | Raw `news_items` for AI-filtered feeds (FR-032 sub-view) |
| POST | `/api/news/items/{id}/read` | Mark `news_items` row as read |
| POST | `/api/news/items/{id}/unread` | Mark `news_items` row as unread |
| POST | `/api/news/views/{id}/read` | Mark `ai_filtered_views` row as read |
| POST | `/api/news/views/{id}/unread` | Mark `ai_filtered_views` row as unread |
| POST | `/api/news/views/{id}/keep` | Set `keep_as_context = true` on `ai_filtered_views` row |
| POST | `/api/news/views/{id}/unkeep` | Set `keep_as_context = false` on `ai_filtered_views` row |
| GET | `/api/news/{feed_name}/export` | Download JSON with `unread_items` + `context_items` for an `ai_filtered` feed (FR-033) |
| POST | `/api/news/{feed_name}/import` | Replace all `ai_filtered_views` for a feed with imported JSON payload (FR-034) |

### Database Interface

All three processes connect via SQLAlchemy using `database.url` from `config.yaml`.

| Process | Reads | Writes |
|---|---|---|
| CLI Ingester | — | `movies`, `series`, `series_episodes`, `news_items`, `feed_health` |
| CLI Filter Processor | `news_items`, `filters` | `filters` (sync), `news_items.matched_filter_id` |
| FastAPI Web UI | `movies`, `series`, `series_episodes`, `news_items`, `ai_filtered_views`, `feed_health`, `filters` | `movies.is_read`, `movies` (enrichment), `series.is_ignored`, `series_episodes.is_read`, `news_items.is_read`, `ai_filtered_views` (full replace on import), `ai_filtered_views.is_read`, `ai_filtered_views.keep_as_context` |

**Concurrency:** SQLite has a single-writer limitation — acceptable since Ingester and Filter Processor run sequentially in the same cron chain, and web app writes are infrequent (read-tracking and occasional imports). MySQL handles concurrent reads and writes without issue.

## 3) Security Model

- **AuthN:** None — localhost-only, single user
- **AuthZ:** None — all actions available to anyone who can reach the port
- **Network:** Web app binds to `127.0.0.1` only (not exposed to network)
- **Secrets management:** Database credentials, API keys, and SMTP config stored in `config.yaml` (file permissions: owner-only read). Not committed to git (`.gitignore`).
- **Input sanitization:** React's default JSX escaping prevents XSS from RSS feed data rendered in the UI. API responses are JSON-only. Import payloads are validated against the expected schema before persisting — raw text is never rendered.

## 4) Operational Model

### Deployment

- Local machine only — no cloud, no containers
- Install: `pip install -r requirements.txt`
- Cron entry added manually (see above)
- External AI tool operated separately by the user — not installed or configured by this application

### Scaling

Not applicable (single user, local machine). MySQL handles concurrent reads well; SQLite is sufficient for the expected data volume.

### Failure Modes

| Failure | Detection | Impact | Recovery |
|---|---|---|---|
| Movie RSS feed down | `feed_health` last_success_at threshold exceeded | No new movies | Auto-retry next cron cycle; email alert after 24h |
| EZTV series feed down | `feed_health` threshold exceeded for `eztv_series` | No new series episodes | Auto-retry next cron cycle; email alert after 24h |
| EZTV title format changed | Parser logs skipped entries (V-027) | Some episodes not ingested | Manual regex update in `fetcher.py` |
| News RSS feed down | Same — per-feed `feed_health` row | No new items for that feed | Auto-retry next cron cycle; email alert after 24h |
| RSS/Atom format changed | Parser logs warning on unexpected structure | Some items not ingested | Manual parser update |
| Enrichment API unavailable | HTTP timeout/error caught | Movie shows without ratings | User retries via "refresh ratings" button |
| Import payload schema invalid | Validation error returned by POST /import | Import rejected; existing ai_filtered_views unchanged | Fix payload and re-upload |
| Import partially malformed | Per-row validation catches bad rows | Valid rows persisted; bad rows skipped and logged | Review logs; re-import corrected payload |
| Database unreachable (MySQL) | SQLAlchemy connection error on startup | Both processes fail to start | Check MySQL service and connection string |
| Web app crash | Process exits | UI unavailable | Restart `python src/webui/main.py` |
| Disk full (SQLite) | Write error | Ingestion fails | Free disk space |

### Backup

- MySQL: `mysqldump` (user's responsibility)
- SQLite: file copy of `.db` file
- Config: tracked in git (minus secrets via `.gitignore`)

## 5) Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.11+ |
| Web framework | FastAPI | latest |
| Frontend rendering | React (CDN — no build step) | 18.x |
| JSX transform | Babel Standalone (CDN) | latest |
| ORM | SQLAlchemy | 2.0+ |
| DB (primary) | MySQL | 8.0+ |
| DB (fallback) | SQLite | 3.x (stdlib) |
| MySQL driver | PyMySQL | latest |
| RSS/Atom parsing | feedparser | latest |
| HTTP client | httpx or requests | latest |
| Config | PyYAML | latest |
| SMTP | smtplib | (stdlib) |
| ASGI server | Uvicorn | latest |

## 6) Non-Functional Requirements

### Availability (NFR-001)
- CLI Ingester tolerates feed failures — logs error, retries next cron cycle
- Web UI is on-demand (not a 24/7 service) — availability is user-controlled
- Import endpoint rejects invalid payloads without modifying existing data

### Performance (NFR-002)
- Web UI queries DB directly — with proper indexes, response <1s for 10k movies
- Filtering and sorting done in SQL where possible, not in Python

### Maintainability (NFR-003)
- Clear separation: `src/cli/` (ingestion + filtering), `src/webui/` (web layer), `src/common/` (shared models, config, DB)

### Cost (NFR-004, C-004, C-009)
- Movie enrichment uses free-tier APIs only (OMDb free tier, TMDb, imdbapi.dev)
- Series records stored as-is from RSS — no enrichment API calls
- No AI service costs incurred by the application (C-004, C-008)

### ~~AI Timeout (NFR-005)~~ — Removed
- No longer applicable; the application does not invoke any AI service

### Export/Import Observability (NFR-006)
- Web UI logs item count included in each export response (unread + context)
- Web UI logs row count received and persisted on each import

## 7) Constraints Compliance Matrix

| Constraint | Implementation |
|---|---|
| C-001 (Python) | Entire stack is Python |
| C-002 (MySQL primary + SQLite fallback) | SQLAlchemy with configurable connection URL |
| C-003 (Three processes) | CLI Ingester (cron step 1) + CLI Filter Processor (cron step 2) + FastAPI Web UI (long-running) |
| C-004 (No paid APIs for movie enrichment) | Free-tier sources only for movies; no AI service costs incurred by the app |
| C-005 (Local SMTP) | `smtplib` with configurable SMTP host/port |
| C-006 (Web UI via FastAPI) | FastAPI serves static React app (CDN-loaded, no build step) + JSON API; Movies, Series, and News tabs |
| C-007 (Config file) | `config.yaml` for all configurable values — feeds, filters, thresholds, series feed URL |
| C-008 (AI integration) | Export/import endpoints on Web UI; app never invokes any AI service directly (ADR-009) |
| C-009 (No paid series APIs) | Series records stored as-is from EZTV RSS; no enrichment API calls |
