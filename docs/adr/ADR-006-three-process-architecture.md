# ADR-006: Three-process architecture (Ingester + Filter Processor + Web UI)

- **Status:** Accepted
- **Date:** 2026-06-15
- **Owners:** Ignacio Bonelli

## Context

The original architecture had two processes: a CLI Ingester (cron-triggered) and a FastAPI Web UI. Adding news feeds with three filter types (unfiltered, regex-filtered, AI-filtered) introduced a distinct batch processing concern that fits neither existing process cleanly. Placing filter logic inside the Ingester would couple fetching with AI calls, making ingestion slow and harder to retry independently. Placing it in the Web UI would make filtering request-driven and stateful rather than batch, complicating the `keep_as_context` re-processing logic for AI-filtered feeds.

## Decision

Split batch work into two sequential cron processes: CLI Ingester (fetch and store raw data) runs first, CLI Filter Processor (apply regex and AI filters, write results) runs immediately after. FastAPI Web UI remains the third, long-running process.

Cron entry: `python src/cli/ingest.py && python src/cli/filter.py`

## Consequences

### Positive
- Clear separation of concerns: fetching vs. filtering vs. viewing
- Filter Processor can be re-run independently after tuning filter patterns or prompts without re-fetching
- AI filtering (potentially slow, NFR-005) does not block ingestion or cause ingester timeouts
- Each process has a single, testable responsibility

### Negative
- Three processes to maintain instead of two (C-003 updated)
- State coordination between Ingester and Filter Processor relies entirely on the shared DB
- Cron must chain both batch processes; if Ingester fails, Filter Processor should not run

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Inline filtering in Ingester | Simpler; single cron entry | Couples fetching and AI calls; slow Claude CLI blocks next ingestion cycle | Rejected — violates separation of concerns; risks cron overlap on slow AI runs |
| On-demand filtering in Web UI | Triggered only when user views news | Results ephemeral; re-processing context logic complex without batch state; UX latency | Rejected — filtering state (keep_as_context, re-processing unread) requires batch tracking |

## Links
- Related requirements: FR-019, FR-022, FR-023, FR-024, NFR-005, C-003
- Related design docs: `docs/02-planning/High-Level-Design.md`
