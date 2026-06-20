# Observability Plan — pelis-feed

## Metrics
- **M-001 (Feed success rate):** Count of successful vs. failed RSS fetch attempts per feed (logged per cron run)
- **M-002 (Enrichment coverage):** Percentage of movies with at least one rating source populated
- **M-003 (Movies ingested):** Total movies in DB, new movies per cron run
- **M-004 (News items ingested):** Items fetched per news feed per cron run (all types)
- **M-005 (Export/Import throughput):** Items included in each export response; rows persisted on each import per AI-filtered feed (NFR-006)

## Logs
- **Required fields:** timestamp, component (ingester/filter/webapp), level, message
- **Format:** Structured logging via Python `logging` module (to stdout + optional file)
- **Key log events:**
  - RSS/Atom fetch success/failure per feed (with HTTP status, entry count)
  - Movie enrichment success/failure (with source name, error reason)
  - Feed downtime alert triggered (feed name, hours since last success)
  - Regex filter pass: items matched vs. total per filtered feed per run
  - Export request: feed name, unread item count, context item count
  - Import request: feed name, rows received, rows persisted, any validation errors
  - Web UI startup/shutdown

## Alerts
- **A-001 (Feed downtime):** Email alert via local SMTP when any feed (movie or news) is unreachable for >24 hours (FR-007)
- **A-002 (Enrichment degradation):** Log warning when >50% of enrichment attempts fail in a single run (informational, no email)
- **A-003 (Import failure):** Log warning when an import payload fails schema validation or DB persistence for an AI-filtered feed (informational, no email)

## Dashboards
- Not applicable for initial version (personal local project)
- Future option: simple stats page in the web app showing feed health, enrichment coverage, and news filter match rates
