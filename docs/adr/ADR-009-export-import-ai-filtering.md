# ADR-009: JSON export/import for AI-filtered news processing

- **Status:** Accepted
- **Date:** 2026-06-19
- **Owners:** Ignacio Bonelli

## Context

ADR-008 established Claude CLI as the mechanism for AI-filtered news processing: the ingester would invoke `claude` directly, passing items as JSON and persisting the output in `ai_filtered_views`. In practice this created tight coupling between the application and a specific AI tool: the CLI had to be installed and authenticated on the same machine, the ingester was responsible for prompt engineering, and any change of AI tool required code changes. The requirement to support different prompts per run, model experimentation, and pre/post-processing of items is better handled outside the application. C-008 is updated to reflect the new approach.

## Decision

Remove all direct AI invocation from the application. Instead, expose two endpoints on the web application: `GET /api/news/{feed}/export` returns a downloadable JSON file of unread `news_items` rows plus `keep_as_context` `ai_filtered_views` rows; `POST /api/news/{feed}/import` accepts a JSON payload in the `ai_filtered_views` format (with `source_item_id` references back to `news_items`) and replaces the existing `ai_filtered_views` rows for that feed. The choice of AI tool, prompt, and processing pipeline is entirely external to the application.

## Consequences

### Positive
- Application has zero dependency on any AI tool, CLI, or API — no installation, authentication, or cost incurred by the app itself
- AI tool can be changed, upgraded, or replaced without touching application code
- The external tool can apply pre-processing, chunking, model selection, or multi-step pipelines freely
- `source_item_id` FK preserves traceability between AI views and original news items
- `keep_as_context` items are included in the export, giving the external tool prior context without any special in-app logic

### Negative
- Processing is no longer automatic — user must manually trigger export, run the external tool, and upload the import
- No in-app timeout or retry logic (the external tool is responsible for its own reliability)
- Requires the user to operate and maintain the external AI pipeline separately

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Keep Claude CLI (ADR-008) | Fully automated; no manual step | Tight coupling to one tool; CLI must be installed and authed on app host; difficult to iterate on prompts | Rejected — operational friction outweighs automation benefit for a personal project |
| Webhook / push model (app calls external URL) | Still automated | Requires the external tool to expose an HTTP endpoint; adds networking complexity | Rejected — adds infrastructure with no clear benefit over pull-based export/import |
| Scheduled background task calling an AI SDK | More control than CLI | Brings AI dependency back into the app; same coupling problem as ADR-008 | Rejected — same reason as keeping Claude CLI |

## Links
- Supersedes: ADR-008
- Related requirements: FR-023, FR-027, FR-033, FR-034, FR-035, FR-036, NFR-006, C-008
- Related design docs: `docs/02-planning/High-Level-Design.md`
- Related ADR: ADR-007 (two-table design this decision builds on)
