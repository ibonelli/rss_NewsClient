# Delivery Plan — pelis-feed

## 1) Scope recap

### In scope
- RSS feed ingestion from `https://yts.ag/rss` (cron-triggered CLI)
- Scheduled polling (~2 hours via system cron)
- SQLite/MySQL database for persistent storage (dual-backend)
- Rating enrichment from free sources (IMDb, RT expert, RT audience)
- FastAPI web application for filtered movie browsing
- Configurable genre-specific filtering rules (config file)
- Read-tracking via web UI (persisted in DB)
- Email alerting (local SMTP) when feed is down >24h

### Out of scope
- Downloading or streaming movies
- Multi-user support / authentication
- Mobile notifications
- Deployment to cloud/remote servers (local only)
- Paid API integrations

## 2) Milestones

| Milestone | Deliverable | Owner |
|---|---|---|
| M1 — Ingestion | CLI process fetches RSS, parses entries, stores in DB. Deduplication works. | Self |
| M2 — Enrichment | Movies are enriched with IMDb + RT ratings from free sources. Failures handled gracefully. | Self |
| M3 — Web Application | FastAPI app serves filtered, grouped movie view. Read-tracking works. | Self |
| M4 — Alerting + Polish | Email alerts on feed downtime >24h. Config-driven filtering is tunable. | Self |

## 3) Work Breakdown (Epics → Stories)

### Epic 1: Ingestion (M1)
- **Story 1.1:** Set up project structure, dependencies, and config loading (FR-016, C-001, C-007)
- **Story 1.2:** Implement RSS feed fetcher with error handling (FR-001, NFR-001)
- **Story 1.3:** Implement database layer with SQLite backend (FR-002, C-002)
- **Story 1.4:** Add MySQL backend support behind same interface (FR-002, C-002)
- **Story 1.5:** Implement deduplication logic — same name/URL merges qualities (FR-003)
- **Story 1.6:** Track feed health — record last successful fetch timestamp (FR-008)

### Epic 2: Enrichment (M2)
- **Story 2.1:** Research and select free rating source(s) — OMDb free tier, TMDb, imdbapi.dev (Q-001)
- **Story 2.2:** Implement IMDb rating enrichment (FR-009)
- **Story 2.3:** Implement RT expert + audience rating enrichment (FR-010, FR-011)
- **Story 2.4:** Graceful failure handling — skip enrichment on errors, retry later (FR-012)

### Epic 3: Web Application (M3)
- **Story 3.1:** FastAPI app skeleton with Jinja2 templates (C-003, C-006)
- **Story 3.2:** Implement filtering logic — genre-specific rating thresholds from config (FR-005, FR-016)
- **Story 3.3:** Implement grouping — same-name movies show together (FR-006)
- **Story 3.4:** Implement year sections (2026→2021) with older movies in summary section (FR-013, FR-014)
- **Story 3.5:** Implement genre-priority ordering within year sections (FR-015)
- **Story 3.6:** Implement read-tracking toggle in UI, persisted to DB (FR-017, FR-018)

### Epic 4: Alerting & Polish (M4)
- **Story 4.1:** Implement feed downtime detection (>24h since last success) (FR-007)
- **Story 4.2:** Send email alert via local SMTP (FR-007, C-005)
- **Story 4.3:** Verify end-to-end flow: ingest → enrich → serve → track

## 4) Dependencies
- **External teams:** None (solo project)
- **Vendors:** Free-tier API access (OMDb/TMDb/imdbapi.dev) — no sign-up may be needed depending on source
- **Environments:** Local machine with Python, system cron, local SMTP server
- **Approvals:** None

## 5) Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Dual DB complexity (SQLite + MySQL) | Higher testing burden, potential ORM differences | Use SQLAlchemy as abstraction layer; test both backends |
| Filter tuning difficulty | Genre-specific thresholds hard to calibrate initially | Make thresholds easily adjustable via config; iterate after first data |
| Free rating APIs may be unreliable | Missing or stale ratings | Support multiple sources; graceful fallback; enrich asynchronously |
| YTS RSS feed format changes | Ingestion breaks silently | Validate parsed fields; alert on parse failures |

## 6) Rollout strategy
- **Direct local deploy** — no staged rollout needed for personal project
- **Cron setup:** Add cron job for ingestion CLI after M1 is verified working
- **Web app:** Run locally on-demand (`pelis serve`) after M3
- **Rollback:** Git-based — revert to previous commit if needed

## 7) Definition of Done (DoD)
- [ ] Code runs without errors for the milestone's scope
- [ ] Basic tests cover happy path
- [ ] HTML view renders correctly (M3+)
- [ ] Config file is documented with example values
