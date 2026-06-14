# High-Level Design (HLD) — pelis-feed

## 1) Overview
- **What:** An automated movie discovery pipeline with a web-based viewer
- **Why:** Eliminate manual RSS browsing by automating ingestion, enrichment, filtering, and presenting quality movies in a clean local UI

## 2) System Context

```
┌─────────────────┐       ┌──────────────────┐       ┌─────────────┐
│  YTS RSS Feed   │──────▶│  CLI Ingester    │──────▶│  Database   │
│ (yts.ag/rss)    │       │  (cron-triggered)│       │ (SQLite/    │
└─────────────────┘       └──────────────────┘       │  MySQL)     │
                                   │                  └──────┬──────┘
                                   ▼                         │
                          ┌──────────────────┐               │
                          │  Rating APIs     │               │
                          │  (OMDb/TMDb/     │               │
                          │   imdbapi.dev)   │               │
                          └──────────────────┘               │
                                                             │
                          ┌──────────────────┐               │
                          │  FastAPI Web App │◀──────────────┘
                          │  (pelis serve)   │
                          └────────┬─────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │  Browser (User)  │
                          └──────────────────┘

                          ┌──────────────────┐
                          │  Local SMTP      │◀── Alert on feed downtime >24h
                          └──────────────────┘
```

- **Actors:** Self (sole user, via browser)
- **External systems:** YTS RSS feed, free rating APIs, local SMTP
- **Trust boundaries:** All local — no authentication needed (single-user, localhost only)

## 3) Proposed Solution

### Components

| Component | Responsibility | Process |
|---|---|---|
| **CLI Ingester** | Fetch RSS, parse, deduplicate, store, enrich, check feed health | Process 1 (cron) |
| **FastAPI Web App** | Serve filtered view, read-tracking, config reload | Process 2 (on-demand) |
| **Database (SQLite/MySQL)** | Persistent storage for movies, ratings, read status, feed health | Shared resource |
| **Config file** | Genre-specific filtering rules, rating thresholds | Shared resource |

### Data Flow

1. **System cron** triggers CLI ingester every ~2 hours
2. CLI fetches RSS XML from `yts.ag/rss`
3. Parser extracts movie entries (title, year, genre, torrent URL, quality)
4. Deduplication: if movie exists (by name or URL), append new quality; otherwise insert
5. Enrichment: for movies missing ratings, query free API(s) for IMDb + RT scores
6. Feed health: record timestamp of last successful fetch
7. Alert check: if last success > 24h ago, send email via SMTP
8. **User runs** `pelis serve` to start FastAPI app
9. Web app reads DB, applies config-based filters, renders grouped/sorted view
10. User marks movies as read → DB toggle → excluded from future views

### Database Schema (Conceptual)

```
movies
├── id (PK)
├── title
├── year
├── genre (comma-separated or JSON array)
├── torrent_url
├── qualities (JSON array: ["720p", "1080p", "2160p"])
├── imdb_rating (nullable float)
├── rt_expert_rating (nullable int, 0-100)
├── rt_audience_rating (nullable int, 0-100)
├── poster_url (nullable)
├── feed_entry_date
├── enrichment_date (nullable)
├── is_read (boolean, default false)
├── created_at
└── updated_at

feed_health
├── id (PK)
├── last_success_at (timestamp)
├── last_attempt_at (timestamp)
└── last_error (nullable text)
```

### Config File (Conceptual — YAML or TOML)

```yaml
filtering:
  default:
    min_imdb: 6.0
    min_rt_expert: 60
    min_rt_audience: 50
  genres:
    action:
      min_imdb: 5.5
    documentary:
      min_imdb: 7.0
      min_rt_expert: 80
    romantic_comedy:
      min_imdb: 5.0

  older_movies:  # >6 years
    min_imdb: 7.5
    min_rt_expert: 75

genre_priority:
  - action
  - romantic_comedy
  - thriller
  - sci-fi
  - drama
  - horror
  - comedy
  - documentary
```

## 4) Alternatives considered

| Option | Description | Why rejected |
|---|---|---|
| Static HTML report | CLI generates a `.html` file; user opens in browser | Cannot support read-tracking without a server or fragile localStorage hacks |
| Monolithic script | Single script that ingests + generates report in one run | Violates C-003 (two-process requirement); harder to schedule independently |
| React SPA + API | Separate frontend and backend | Over-engineered for a personal project; FastAPI + Jinja2 is sufficient |

## 5) Key Decisions

- **ADR candidate:** Switch from static HTML report to FastAPI web app (decided during Phase 2 planning)
- **ADR candidate:** Use SQLAlchemy as database abstraction layer to support dual-backend (SQLite + MySQL)

## 6) Non-functional impacts

### Availability (NFR-001)
- CLI ingester tolerates feed failures — logs error, retries next cron cycle
- Web app is on-demand (not a 24/7 service) — availability is user-controlled

### Performance (NFR-002)
- Web app queries DB directly — with proper indexes, <1s response for 10k movies
- Filtering/sorting done in SQL where possible, not in Python

### Maintainability (NFR-003)
- Clear separation: `ingester/`, `webapp/`, `shared/` (models, config)
- SQLAlchemy models shared between both processes

### Cost (NFR-004, C-004)
- All enrichment uses free-tier APIs only
- No cloud hosting costs (runs locally)

## 7) Constraints acknowledgment

| Constraint | How addressed |
|---|---|
| C-001 (Python) | Entire codebase in Python |
| C-002 (SQLite/MySQL) | SQLAlchemy with configurable connection string |
| C-003 (Two processes) | CLI ingester + FastAPI web app |
| C-004 (No paid APIs) | Only free-tier sources for enrichment |
| C-005 (Local SMTP) | `smtplib` for alerting |
| C-006 (Web UI) | FastAPI + Jinja2 templates |
| C-007 (Config file) | YAML/TOML config for filtering rules |
