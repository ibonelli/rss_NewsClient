# Constraints Register — pelis-feed

## Purpose
List constraints that are non-negotiable. This is a primary AI context document.

## Constraints
- **C-001 (Language):** MUST use Python.
- **C-002 (Database):** MUST support MySQL (primary) and SQLite (fallback) via SQLAlchemy abstraction. MySQL is the default when a server is available.
- **C-003 (Architecture):** MUST have two separate processes: (1) CLI scheduler/ingester (cron-triggered), (2) FastAPI web application for viewing and tracking.
- **C-004 (Cost):** MUST NOT use paid APIs for movie rating enrichment. Claude CLI is explicitly permitted for AI-filtered news feeds.
- **C-005 (Email):** MUST use local SMTP for alerting.
- **C-006 (Report format):** MUST serve a web-based UI via FastAPI for viewing and tracking both movies and news.
- **C-007 (Configuration):** Filtering rules and feed definitions MUST be configurable via file, not hardcoded.
- **C-008 (AI tool):** AI-filtered news feeds MUST use the Claude CLI (`claude` command-line tool) for processing; no other AI service may be substituted without an ADR.

## Forbidden Solutions (Explicit)
- **F-001:** Do NOT use paid API tiers for movie rating enrichment (OMDb paid, TMDb paid, etc.).
- **F-002:** Do NOT download or stream movie content.
- **F-003:** Do NOT hardcode filtering thresholds or feed definitions in source code.
- **F-004:** Do NOT use paid third-party news enrichment or classification APIs other than Claude CLI.

## Notes / Rationale
- Personal project with zero budget for external services (movie enrichment); Claude CLI costs are accepted for AI news filtering.
- SQLite chosen for simplicity when MySQL is not available; MySQL preferred when a server is accessible.
- Two-process split allows independent scheduling of ingestion vs. report generation.
