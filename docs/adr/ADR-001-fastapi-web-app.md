# ADR-001: Replace static HTML report with FastAPI web application

- **Status:** Accepted
- **Date:** 2026-05-21
- **Owners:** Self

## Context

The original design (FR-004, C-006) specified a single static HTML file as the report output. However, read-tracking (FR-017, FR-018) requires persisting user interactions — marking movies as "read" so they are excluded from future views. A static HTML file cannot reliably persist state: localStorage is browser-local and fragile, and a sidecar file requires running CLI commands instead of clicking a button. A minimal web server provides proper state persistence with minimal added complexity.

## Decision

Replace the static HTML report with a minimal FastAPI web application (using Jinja2 templates) that serves the same filtered, grouped movie view dynamically and provides read-tracking via in-page toggles persisted to the database.

## Consequences

### Positive
- Read-tracking is properly persisted in the database
- UI interaction is natural (click to mark as read) rather than CLI-based
- Same visual output as static HTML, but dynamic
- Config changes can take effect without regenerating a file
- Foundation for future enhancements (search, pagination) if ever needed

### Negative
- Requires running a process (`pelis serve`) instead of opening a file
- Adds FastAPI + Jinja2 + Uvicorn as dependencies
- Slightly more complex deployment (a running process vs. a file)

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Static HTML + localStorage | Zero dependencies, just open a file | Tracking tied to one browser, lost on clear, no cross-device | Fragile, violates FR-018 (persistence) |
| Static HTML + CLI mark-read | No web server needed | Poor UX — requires knowing movie IDs, running commands | Friction too high for regular use |
| Static HTML + micro-API | Mostly static, only tracking needs server | Hybrid complexity — two serving modes, confusing | Overly complex for the benefit |
| React SPA + API backend | Professional, highly interactive | Over-engineered for single-user personal project | Violates simplicity goal |

## Links
- Related requirements: FR-004, FR-017, FR-018, C-006
- Related design docs: `docs/02-planning/High-Level-Design.md`
