# Observability Plan — pelis-feed

## Metrics
- **M-001 (Feed success rate):** Count of successful vs. failed RSS fetch attempts per feed (logged per cron run)
- **M-002 (Enrichment coverage):** Percentage of movies with at least one rating source populated
- **M-003 (Movies ingested):** Total movies in DB, new movies per cron run
- **M-004 (News items ingested):** Items fetched per news feed per cron run (all types)
- **M-005 (AI filter throughput):** Items sent to Claude CLI vs. items returned per AI-filtered feed per run (NFR-006)

## Logs
- **Required fields:** timestamp, component (ingester/filter/webapp), level, message
- **Format:** Structured logging via Python `logging` module (to stdout + optional file)
- **Key log events:**
  - RSS/Atom fetch success/failure per feed (with HTTP status, entry count)
  - Movie enrichment success/failure (with source name, error reason)
  - Feed downtime alert triggered (feed name, hours since last success)
  - Regex filter pass: items matched vs. total per filtered feed per run
  - Claude CLI invocation: feed name, items sent, items returned, duration, timeout events
  - Filter Processor startup: `filters` table sync result (added/updated/unchanged per feed)
  - Web UI startup/shutdown

## Alerts
- **A-001 (Feed downtime):** Email alert via local SMTP when any feed (movie or news) is unreachable for >24 hours (FR-007)
- **A-002 (Enrichment degradation):** Log warning when >50% of enrichment attempts fail in a single run (informational, no email)
- **A-003 (Claude CLI failure):** Log warning when Claude CLI times out or returns unparseable output for an AI-filtered feed (informational, no email)

## Dashboards
- Not applicable for initial version (personal local project)
- Future option: simple stats page in the web app showing feed health, enrichment coverage, and news filter match rates
