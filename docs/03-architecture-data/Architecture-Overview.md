# Architecture Overview — pelis-feed

## 1) Boundaries & Ownership

| Component | Responsibility | Runtime |
|---|---|---|
| **CLI Ingester** (`src/cli/main.py`) | Fetch all RSS/Atom feeds (movie + news), parse, deduplicate (movies), store raw data to `movies` and `news_items`, update feed health | Cron-triggered process (runs and exits, step 1) |
| **CLI Filter Processor** (`src/cli/filter.py`) | Sync `filters` table from config; regex-match `news_items` for filtered feeds; invoke Claude CLI for AI-filtered feeds; upsert `ai_filtered_views`; upsert `categories` | Cron-triggered process (runs and exits, step 2 — after Ingester) |
| **FastAPI Web UI** (`src/webui/main.py`) | JSON API for movies and news (filtering, read-tracking, on-demand enrichment) + static React frontend | Long-running local process (on-demand) |
| **Database** (MySQL/SQLite) | Persistent state for all data | Shared resource |
| **Config file** (`config.yaml`) | Feed definitions, filter patterns, rating thresholds, Claude CLI settings, connection strings | Shared resource (read by all three processes) |

### Project Structure

```
src/
├── cli/
│   ├── main.py         # Ingester entry point
│   ├── filter.py       # Filter Processor entry point
│   ├── fetcher.py      # RSS/Atom fetch + parse (movies and news)
│   ├── dedup.py        # Movie deduplication logic
│   └── alerter.py      # Feed health check + SMTP alert
├── webui/
│   ├── main.py         # Uvicorn entry point
│   ├── app.py          # FastAPI app factory + static file mounting
│   ├── routes.py       # JSON API route handlers
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
| `python src/cli/main.py` | Fetch all feeds, store raw data, update feed health | Every ~2h (cron step 1) |
| `python src/cli/filter.py` | Sync filters, apply regex + AI filtering | Every ~2h (cron step 2, immediately after Ingester) |
| `python src/webui/main.py` | Start FastAPI web app (Uvicorn) | Manual, on-demand |

**Cron entry:** `0 */2 * * * python src/cli/main.py && python src/cli/filter.py`

### Web App Routes (FastAPI — JSON API)

**Movies**

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serve static React frontend (`index.html`) |
| GET | `/api/movies` | Filtered movie list grouped by year and genre priority |
| POST | `/api/movies/{id}/read` | Mark movie as read |
| POST | `/api/movies/{id}/unread` | Mark movie as unread |
| POST | `/api/movies/{id}/enrich` | Trigger on-demand rating enrichment |
| GET | `/api/health` | Feed health status for all feeds |
| GET | `/static/*` | Static assets (JS, CSS) |

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

### Database Interface

All three processes connect via SQLAlchemy using `database.url` from `config.yaml`.

| Process | Reads | Writes |
|---|---|---|
| CLI Ingester | — | `movies`, `news_items`, `feed_health` |
| CLI Filter Processor | `news_items`, `filters`, `ai_filtered_views` (keep_as_context items), `categories` | `filters`, `news_items.matched_filter_id`, `ai_filtered_views`, `categories` |
| FastAPI Web UI | `movies`, `news_items`, `ai_filtered_views`, `categories`, `feed_health`, `filters` | `movies.is_read`, `movies` (enrichment), `news_items.is_read`, `ai_filtered_views.is_read`, `ai_filtered_views.keep_as_context` |

**Concurrency:** SQLite has a single-writer limitation — acceptable since Ingester and Filter Processor run sequentially in the same cron chain, and web app writes are infrequent (read-tracking only). MySQL handles concurrent reads and writes without issue.

## 3) Security Model

- **AuthN:** None — localhost-only, single user
- **AuthZ:** None — all actions available to anyone who can reach the port
- **Network:** Web app binds to `127.0.0.1` only (not exposed to network)
- **Secrets management:** Database credentials, API keys, and SMTP config stored in `config.yaml` (file permissions: owner-only read). Not committed to git (`.gitignore`).
- **Input sanitization:** React's default JSX escaping prevents XSS from RSS feed data rendered in the UI. API responses are JSON-only. Claude CLI output is parsed as structured JSON before persisting — raw text is never rendered.

## 4) Operational Model

### Deployment

- Local machine only — no cloud, no containers
- Install: `pip install -r requirements.txt`
- Cron entry added manually (see above)
- Claude CLI must be installed and authenticated on the local machine (C-008)

### Scaling

Not applicable (single user, local machine). MySQL handles concurrent reads well; SQLite is sufficient for the expected data volume.

### Failure Modes

| Failure | Detection | Impact | Recovery |
|---|---|---|---|
| Movie RSS feed down | `feed_health` last_success_at threshold exceeded | No new movies | Auto-retry next cron cycle; email alert after 24h |
| News RSS feed down | Same — per-feed `feed_health` row | No new items for that feed | Auto-retry next cron cycle; email alert after 24h |
| RSS/Atom format changed | Parser logs warning on unexpected structure | Some items not ingested | Manual parser update |
| Enrichment API unavailable | HTTP timeout/error caught | Movie shows without ratings | User retries via "refresh ratings" button |
| Claude CLI not installed/authenticated | Subprocess error at Filter Processor startup | AI-filtered feeds skipped for cycle | Log clearly; fix authentication; retry next cycle |
| Claude CLI timeout | Configurable per-feed `claude_timeout_seconds` exceeded | AI-filtered feed skipped for cycle | Log timeout; retry next cycle |
| Claude CLI returns malformed JSON | JSON parse error caught | AI-filtered feed skipped for cycle | Log error with raw output; retry next cycle |
| Database unreachable (MySQL) | SQLAlchemy connection error on startup | All three processes fail to start | Check MySQL service and connection string |
| Filter Processor crash | Process exits non-zero | Filtering skipped for cycle | Check logs; fix and re-run manually |
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
| AI filtering | Claude CLI (`claude`) | current authenticated version |

## 6) Non-Functional Requirements

### Availability (NFR-001)
- CLI Ingester tolerates feed failures — logs error, retries next cron cycle
- CLI Filter Processor tolerates Claude CLI failures per feed — logs and skips that feed, does not crash
- Web UI is on-demand (not a 24/7 service) — availability is user-controlled

### Performance (NFR-002)
- Web UI queries DB directly — with proper indexes, response <1s for 10k movies
- Filtering and sorting done in SQL where possible, not in Python

### Maintainability (NFR-003)
- Clear separation: `src/cli/` (ingestion + filtering), `src/webui/` (web layer), `src/common/` (shared models, config, DB)

### Cost (NFR-004)
- Movie enrichment uses free-tier APIs only (OMDb free tier, TMDb, imdbapi.dev)
- Claude CLI costs accepted for AI-filtered news feeds (C-004, C-008)

### AI Timeout (NFR-005)
- `claude_timeout_seconds` configurable per AI-filtered feed in `config.yaml`
- Filter Processor enforces timeout via subprocess timeout; logs and skips that feed on timeout

### AI Observability (NFR-006)
- Filter Processor logs item count sent to and received from Claude CLI per feed per run

## 7) Constraints Compliance Matrix

| Constraint | Implementation |
|---|---|
| C-001 (Python) | Entire stack is Python |
| C-002 (MySQL primary + SQLite fallback) | SQLAlchemy with configurable connection URL |
| C-003 (Three processes) | CLI Ingester (cron step 1) + CLI Filter Processor (cron step 2) + FastAPI Web UI (long-running) |
| C-004 (No paid APIs for movie enrichment) | Free-tier sources only for movies; Claude CLI accepted for news AI filtering |
| C-005 (Local SMTP) | `smtplib` with configurable SMTP host/port |
| C-006 (Web UI via FastAPI) | FastAPI serves static React app (CDN-loaded, no build step) + JSON API |
| C-007 (Config file) | `config.yaml` for all configurable values — feeds, filters, thresholds, Claude prompts |
| C-008 (Claude CLI) | AI-filtered feeds invoke `claude` CLI subprocess; no other AI service without ADR |
