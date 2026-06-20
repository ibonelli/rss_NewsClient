# Constraints Register — pelis-feed

## Purpose
List constraints that are non-negotiable. This is a primary AI context document.

## Constraints
- **C-001 (Language):** MUST use Python.
- **C-002 (Database):** MUST support MySQL (primary) and SQLite (fallback) via SQLAlchemy abstraction. MySQL is the default when a server is available.
- **C-003 (Architecture):** MUST have three separate processes: (1) CLI Ingester (cron-triggered), (2) CLI Filter Processor (cron-triggered, runs after Ingester), (3) FastAPI web application for viewing and tracking.
- **C-004 (Cost):** MUST NOT use paid APIs for movie or series metadata enrichment.
- **C-005 (Email):** MUST use local SMTP for alerting.
- **C-006 (UI):** MUST serve a web-based UI via FastAPI for viewing and tracking movies, series, and news.
- **C-007 (Configuration):** Filtering rules and feed definitions MUST be configurable via file, not hardcoded.
- **C-008 (AI integration):** AI-filtered news feeds MUST support JSON export of unprocessed items (for external AI processing) and JSON import of results. The application MUST NOT invoke any AI tool or external AI service directly.
- **C-009 (Series enrichment):** MUST NOT use paid APIs for series metadata enrichment. Series records are stored as ingested from the RSS feed only.

## Forbidden Solutions (Explicit)
- **F-001:** Do NOT use paid API tiers for movie rating enrichment (OMDb paid, TMDb paid, etc.).
- **F-002:** Do NOT download or stream movie or series content.
- **F-003:** Do NOT hardcode filtering thresholds or feed definitions in source code.
- **F-004:** Do NOT invoke any AI service (including Claude CLI) directly from within the application.
- **F-005:** Do NOT use paid APIs for series metadata enrichment.

## Notes / Rationale
- Personal project with zero budget for external services.
- SQLite chosen for simplicity when MySQL is not available; MySQL preferred when a server is accessible.
- Two-process split allows independent scheduling of ingestion vs. web serving.
- AI classification is intentionally decoupled from the application; the export/import pattern keeps the app free from any dependency on a specific AI tool or service.
