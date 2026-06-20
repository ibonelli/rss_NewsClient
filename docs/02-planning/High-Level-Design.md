# High-Level Design (HLD) — pelis-feed

## 1) Overview
- **What:** An automated movie and news discovery pipeline with a web-based viewer
- **Why:** Eliminate manual RSS browsing by automating ingestion, filtering (regex and AI-assisted), and presenting quality movies and relevant news in a clean local UI

## 2) System Context

```
┌─────────────────┐    ┌─────────────────────────────┐
│  YTS RSS Feed   │───▶│   CLI Ingester (cron)        │──▶ movies
└─────────────────┘    │                              │──▶ news_items
┌─────────────────┐    │   fetches all feeds;         │──▶ feed_health
│  News RSS/Atom  │───▶│   regex matching inline      │──▶ matched_filter
│  Feeds (n)      │    └──────────────┬───────────────┘
└─────────────────┘                   │
                            ┌─────────┴─────────┐
                            │     Database      │
                            │  (SQLite/MySQL)   │
                            └────────┬──────────┘
                                     │
              ┌──────────────────────┴─────────────────────┐
              ▼                                             ▼
┌──────────────────────────┐                 ┌─────────────────────┐
│  FastAPI Web UI          │──▶ Browser      │  Rating APIs        │
│  (long-running)          │                 │  (OMDb/TMDb/etc.)   │
│                          │                 └─────────────────────┘
│  GET /{feed}/export ─────┼──▶ JSON download
│  POST /{feed}/import ◀───┼─── JSON upload
└────────────┬─────────────┘
             │ export                 ▲ import
             ▼                        │
┌──────────────────────────┐          │
│  External AI Tool        │──────────┘
│  (user-operated;         │
│   not part of this app)  │
└──────────────────────────┘

┌─────────────────────┐
│  Local SMTP         │◀── feed downtime >24h
└─────────────────────┘
```

- **Actors:** Self (sole user, via browser)
- **External systems:** YTS RSS feed, news RSS/Atom feeds, free rating APIs, local SMTP, external AI tool (user-operated separately)
- **Trust boundaries:** All local — no authentication needed (single-user, localhost only)

## 3) Proposed Solution

### Components

| Component | Responsibility | Process |
|---|---|---|
| **CLI Ingester** | Fetch all RSS/Atom feeds (movie + news), parse, deduplicate (movies), store raw data, apply regex matching for `filtered` feeds, check feed health | Process 1 (cron) |
| **FastAPI Web UI** | Serve filtered movie view, news tab with filtered/AI-filtered/raw sub-views, read-tracking, on-demand movie enrichment, AI-filtered export (`GET`) and import (`POST`) endpoints | Process 2 (long-running) |
| **Database (SQLite/MySQL)** | Persistent storage for all data | Shared resource |
| **Config file** | Feed definitions, filter rules, rating thresholds | Shared resource |
| **External AI Tool** | Consumes export JSON; produces import JSON; operated entirely outside this application | External (user-operated) |

### Data Flow

**Movie pipeline:**
1. System cron triggers CLI Ingester every ~2 hours
2. Ingester fetches RSS XML from `yts.ag/rss`
3. Parser extracts movie entries; deduplication merges quality variants
4. Feed health timestamp recorded per feed
5. Alert check: if last success >24h ago, send email via SMTP

**News pipeline (runs in same cron invocation, after movies):**
6. Ingester fetches each configured news feed (RSS/Atom)
7. All items stored to `news_items` regardless of feed type
8. For `filtered` feeds: regex matching runs inline; `matched_filter_id` written on matches
9. Feed health recorded per news feed

**Web UI (on-demand):**
10. User opens browser; FastAPI reads DB, applies config-based movie filters, renders grouped/sorted view
11. User marks movies or news as read → DB toggle
12. User triggers movie enrichment → on-demand OMDb/TMDb API call

**AI-filtered export/import (user-triggered via browser):**
13. User clicks Export in News tab → `GET /api/news/{feed}/export` → JSON download with two sections: `unread_items` (news_items where is_read = false) and `context_items` (ai_filtered_views where keep_as_context = true)
14. User runs exported JSON through external AI tool (outside the app)
15. User uploads result via News tab → `POST /api/news/{feed}/import` → all existing `ai_filtered_views` for that feed are deleted and replaced with imported rows; each row carries `source_item_id` FK referencing its originating `news_items` row

### Database Schema (Conceptual)

```
movies
├── id (PK)
├── title
├── year
├── genres (JSON array)
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
├── feed_name
├── last_success_at (timestamp)
├── last_attempt_at (timestamp)
└── last_error (nullable text)

news_items
├── id (PK)
├── feed_name
├── title
├── url
├── published_at
├── full_content (text)
├── ingested_at
├── is_read (boolean, default false)      -- used by unfiltered and filtered feeds
└── matched_filter_id (FK → filters.id, nullable)

filters
├── id (PK)
├── feed_name
├── name                                  -- human-readable ("vulnerabilities")
├── pattern                               -- regex string
└── created_at

ai_filtered_views
├── id (PK)
├── source_item_id (FK → news_items.id)
├── feed_name
├── title
├── url
├── published_at
├── category (text)
├── summary (text)
├── tags (JSON array)
├── is_read (boolean, default false)
├── keep_as_context (boolean, default false)
└── ingested_at (timestamp)
```

### Config File (Conceptual — YAML)

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
```

## 4) Alternatives considered

| Option | Description | Why rejected |
|---|---|---|
| Static HTML report | CLI generates a `.html` file; user opens in browser | Cannot support read-tracking without a server or fragile localStorage hacks |
| Monolithic script | Single script that ingests + filters + generates report in one run | Harder to schedule independently; regex and AI processing concerns mixed |
| React SPA + API | Separate frontend and backend | Over-engineered for a personal project; FastAPI + CDN React is sufficient |
| Claude CLI invoked by app | App calls `claude` directly during ingestion or on-demand | Tight coupling to one AI tool; requires CLI installed/authenticated on app host; superseded by ADR-009 |

## 5) Key Decisions

- See ADR-001 (FastAPI web app), ADR-002 (SQLAlchemy), ADR-003 (on-demand enrichment), ADR-004 (React CDN), ADR-005 (src directory split), ADR-006 (process architecture), ADR-007 (two-table design), ADR-009 (export/import replaces Claude CLI — supersedes ADR-008)

## 6) Non-functional impacts

### Availability (NFR-001)
- CLI Ingester tolerates feed failures — logs error, retries next cron cycle
- CLI Filter Processor tolerates Claude CLI failures per feed — logs and skips, does not crash
- Web UI is on-demand (not a 24/7 service) — availability is user-controlled

### Performance (NFR-002)
- Web UI queries DB directly — with proper indexes, <1s response for 10k movies
- Filtering/sorting done in SQL where possible, not in Python

### Maintainability (NFR-003)
- Clear separation: `src/cli/ingest.py`, `src/cli/filter.py`, `src/webui/`, `src/common/` (models, config)

### Cost (NFR-004, C-004)
- Movie enrichment uses free-tier APIs only
- No AI service costs incurred by the application (external tool is user-operated)

### ~~AI Timeout (NFR-005)~~ — Removed
- No longer applicable; the application does not invoke any AI service

### Export/Import Observability (NFR-006)
- Web UI logs item count included in each export response
- Web UI logs row count persisted on each import

## 7) Constraints acknowledgment

| Constraint | How addressed |
|---|---|
| C-001 (Python) | Entire codebase in Python |
| C-002 (SQLite/MySQL) | SQLAlchemy with configurable connection string |
| C-003 (Three processes) | CLI Ingester (cron step 1) + CLI Filter Processor (cron step 2) + FastAPI Web UI |
| C-004 (No paid APIs for enrichment) | Only free-tier sources for movie enrichment; no AI service costs incurred by the app |
| C-005 (Local SMTP) | `smtplib` for alerting |
| C-006 (Web UI) | FastAPI + CDN React |
| C-007 (Config file) | YAML config for filtering rules, feed definitions, filter patterns |
| C-008 (AI integration) | Export/import endpoints on the Web UI; app never invokes any AI service directly (see ADR-009) |
