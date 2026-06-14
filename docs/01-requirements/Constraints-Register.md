# Constraints Register — pelis-feed

## Purpose
List constraints that are non-negotiable. This is a primary AI context document.

## Constraints
- **C-001 (Language):** MUST use Python.
- **C-002 (Database):** MUST support MySQL (primary) and SQLite (fallback) via SQLAlchemy abstraction. MySQL is the default when a server is available.
- **C-003 (Architecture):** MUST have two separate processes: (1) CLI scheduler/ingester (cron-triggered), (2) FastAPI web application for viewing and tracking.
- **C-004 (Cost):** MUST NOT use paid APIs for data enrichment.
- **C-005 (Email):** MUST use local SMTP for alerting.
- **C-006 (Report format):** MUST serve a web-based UI via FastAPI for viewing and tracking movies.
- **C-007 (Configuration):** Filtering rules MUST be configurable via file, not hardcoded.

## Forbidden Solutions (Explicit)
- **F-001:** Do NOT use paid API tiers (OMDb paid, TMDb paid, etc.).
- **F-002:** Do NOT download or stream movie content.
- **F-003:** Do NOT hardcode filtering thresholds in source code.

## Notes / Rationale
- Personal project with zero budget for external services.
- SQLite chosen for simplicity when MySQL is not available; MySQL preferred when a server is accessible.
- Two-process split allows independent scheduling of ingestion vs. report generation.
