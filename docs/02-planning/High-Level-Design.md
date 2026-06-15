# High-Level Design (HLD) — pelis-feed

## 1) Overview
- **What:** An automated movie and news discovery pipeline with a web-based viewer
- **Why:** Eliminate manual RSS browsing by automating ingestion, filtering (regex and AI-assisted), and presenting quality movies and relevant news in a clean local UI

## 2) System Context

```
┌─────────────────┐    ┌─────────────────────┐
│  YTS RSS Feed   │───▶│                     │
└─────────────────┘    │   CLI Ingester      │──▶ movies
┌─────────────────┐    │   (cron, step 1)    │──▶ news_items
│  News RSS/Atom  │───▶│                     │──▶ feed_health
│  Feeds (n)      │    └─────────────────────┘
└─────────────────┘               │
                         (runs next in cron)
                                  ▼
                       ┌─────────────────────┐
                       │   CLI Filter        │──▶ news_items.matched_filter_id
                       │   Processor         │──▶ ai_filtered_views
                       │   (cron, step 2)    │
                       │  ┌───────────────┐  │
                       │  │  Claude CLI   │  │
                       │  └───────────────┘  │
                       └─────────────────────┘
                                  │
                       ┌──────────┴──────────┐
                       │      Database       │
                       │   (SQLite/MySQL)    │
                       └──────────┬──────────┘
                                  │
                       ┌─────────────────────┐    ┌──────────────┐
                       │  Rating APIs        │    │  FastAPI     │
                       │  (OMDb/TMDb/etc.)   │    │  Web UI      │──▶ Browser
                       └──────────┬──────────┘    │  (Process 3) │
                                  │               └──────────────┘
                                  ▼
                       ┌─────────────────────┐
                       │  Local SMTP         │◀── feed downtime >24h
                       └─────────────────────┘
```

- **Actors:** Self (sole user, via browser)
- **External systems:** YTS RSS feed, news RSS/Atom feeds, free rating APIs, Claude CLI, local SMTP
- **Trust boundaries:** All local — no authentication needed (single-user, localhost only)

## 3) Proposed Solution

### Components

| Component | Responsibility | Process |
|---|---|---|
| **CLI Ingester** | Fetch all RSS/Atom feeds (movie + news), parse, deduplicate (movies), store raw data, check feed health | Process 1 (cron, step 1) |
| **CLI Filter Processor** | Sync `filters` table from config; apply regex filters to `news_items`; invoke Claude CLI for AI-filtered feeds; upsert `ai_filtered_views` | Process 2 (cron, step 2) |
| **FastAPI Web UI** | Serve filtered movie view, news tab with filtered/AI-filtered/raw sub-views, read-tracking, on-demand movie enrichment | Process 3 (long-running) |
| **Database (SQLite/MySQL)** | Persistent storage for all data | Shared resource |
| **Config file** | Feed definitions, filter rules, rating thresholds, Claude CLI settings | Shared resource |

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
8. Feed health recorded per news feed

**Filter Processor (cron step 2, runs after Ingester):**
9. Syncs `filters` table from config (upsert by feed_name + name)
10. Regex pass: for each filtered feed, matches `news_items` against `filters` table; writes `matched_filter_id` FK on matches
11. AI pass: for each AI-filtered feed, collects items with no `ai_filtered_views` row (never processed) OR `ai_filtered_views.is_read = false` (unread — re-evaluate); collects `keep_as_context = true` items as background; sends combined JSON to Claude CLI; upserts `ai_filtered_views` for returned items

**Web UI (on-demand):**
12. User opens browser; FastAPI reads DB, applies config-based movie filters, renders grouped/sorted view
13. User marks movies or news as read → DB toggle
14. User triggers movie enrichment → on-demand OMDb/TMDb API call

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
├── news_item_id (FK → news_items.id)
├── feed_name
├── category (text)
├── summary (text)
├── tags (JSON array)
├── is_read (boolean, default false)
├── keep_as_context (boolean, default false)
└── last_filtered_at (timestamp)
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
    claude_prompt: |
      You are filtering a news feed for relevance to AI research and engineering.
      Return only items worth reading, with a category, one-sentence summary, and tags.
      Respond as a JSON array matching the input schema.
    claude_timeout_seconds: 60
```

## 4) Alternatives considered

| Option | Description | Why rejected |
|---|---|---|
| Static HTML report | CLI generates a `.html` file; user opens in browser | Cannot support read-tracking without a server or fragile localStorage hacks |
| Monolithic script | Single script that ingests + filters + generates report in one run | Violates C-003 (three-process requirement); harder to schedule independently |
| React SPA + API | Separate frontend and backend | Over-engineered for a personal project; FastAPI + CDN React is sufficient |
| AI filtering in web UI (on-demand) | Trigger Claude CLI from browser on demand | Filter results would be ephemeral; re-processing context logic is complex without batch state |

## 5) Key Decisions

- See ADR-001 (FastAPI web app), ADR-002 (SQLAlchemy), ADR-003 (on-demand enrichment), ADR-004 (React CDN), ADR-005 (src directory split)
- ADR candidate: three-process split (Ingester + Filter Processor + Web UI)
- ADR candidate: AI-filtered feeds use two-table design (`news_items` + `ai_filtered_views`)
- ADR candidate: Claude CLI chosen for AI-filtered news processing

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
- Claude CLI costs accepted for AI-filtered news feeds (personal project budget decision)

### AI Timeout (NFR-005)
- `claude_timeout_seconds` configurable per AI-filtered feed in config
- Filter Processor logs timeout and skips that feed's AI pass for the cycle

### AI Observability (NFR-006)
- Filter Processor logs item count sent to and received from Claude CLI per feed per run

## 7) Constraints acknowledgment

| Constraint | How addressed |
|---|---|
| C-001 (Python) | Entire codebase in Python |
| C-002 (SQLite/MySQL) | SQLAlchemy with configurable connection string |
| C-003 (Three processes) | CLI Ingester (cron step 1) + CLI Filter Processor (cron step 2) + FastAPI Web UI |
| C-004 (No paid APIs for enrichment) | Only free-tier sources for movie enrichment; Claude CLI permitted for news AI filtering |
| C-005 (Local SMTP) | `smtplib` for alerting |
| C-006 (Web UI) | FastAPI + CDN React |
| C-007 (Config file) | YAML config for filtering rules, feed definitions, filter patterns |
| C-008 (Claude CLI) | AI-filtered feeds invoke `claude` CLI; no substitution without ADR |
