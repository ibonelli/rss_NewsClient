# Observability Plan — pelis-feed

## Metrics
- **M-001 (Feed success rate):** Count of successful vs. failed RSS fetch attempts (logged per cron run)
- **M-002 (Enrichment coverage):** Percentage of movies with at least one rating source populated
- **M-003 (Movies ingested):** Total movies in DB, new movies per day/week

## Logs
- **Required fields:** timestamp, component (ingester/webapp), level, message
- **Format:** Structured logging via Python `logging` module (to stdout + optional file)
- **Key log events:**
  - RSS fetch success/failure (with HTTP status, entry count)
  - Enrichment success/failure per movie (with source name, error reason)
  - Feed downtime alert triggered
  - Web app startup/shutdown

## Alerts
- **A-001 (Feed downtime):** Email alert via local SMTP when feed is unreachable for >24 hours (FR-007)
- **A-002 (Enrichment degradation):** Log warning when >50% of enrichment attempts fail in a single run (informational, no email)

## Dashboards
- Not applicable for initial version (personal local project)
- Future option: simple stats page in the web app showing feed health and enrichment coverage
