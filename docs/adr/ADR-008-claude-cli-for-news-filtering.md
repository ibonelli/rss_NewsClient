# ADR-008: Claude CLI for AI-filtered news processing

- **Status:** Accepted
- **Date:** 2026-06-15
- **Owners:** Ignacio Bonelli

## Context

AI-filtered news feeds require natural language processing to filter, summarize, and categorize news items in batch. Options fall into three categories: cloud AI APIs/CLIs, local models, and scraping/rule-based approaches. The project's C-004 constraint forbids paid APIs for movie enrichment, but explicitly accepts Claude CLI costs for news filtering as a deliberate personal project trade-off (C-004 updated, C-008 added). The key requirements are: high-quality summarization and classification (FR-023, FR-024, FR-027), a configurable prompt per feed (C-007), and a timeout mechanism (NFR-005).

## Decision

Use the Claude CLI (`claude` command-line tool) to process AI-filtered news feeds. The Filter Processor serializes pending/unread items plus context items as JSON, invokes `claude` with a per-feed configurable prompt, and parses the returned JSON array into `ai_filtered_views` rows.

## Consequences

### Positive
- High-quality summarization and classification without running local infrastructure
- Prompt is fully configurable per feed in `config.yaml` (C-007 satisfied)
- No model to host or maintain locally
- Easy to iterate on prompts and test in isolation

### Negative
- Incurs Claude API usage costs per run (accepted trade-off for this project)
- Requires Claude CLI installed and authenticated on the local machine at runtime (C-008)
- Network dependency — AI-filtered feeds silently skip if offline or rate-limited
- AI output format variability requires strict prompt engineering and JSON validation before persisting

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Ollama / local model | No cost; works offline | Lower summarization quality; significant local CPU/GPU resource usage; model maintenance burden | Rejected — quality trade-off not acceptable for the intended use case |
| Anthropic Python SDK (direct) | Same model quality; more control over retries and streaming | More code to maintain vs. CLI; functionally equivalent outcome | Rejected — CLI is simpler to invoke from a batch script; no material advantage |
| OpenAI API | Comparable quality | Different cost structure; requires separate API key management | Rejected — no technical reason; Claude preference |
| Rule-based / keyword filter | No cost; deterministic | Cannot summarize or categorize meaningfully; already covered by the regex `filtered` feed type | Rejected — does not meet the summarization and classification requirements |

## Links
- Related requirements: FR-023, FR-024, FR-027, NFR-005, NFR-006, C-004, C-007, C-008
- Related design docs: `docs/02-planning/High-Level-Design.md`
- Related ADR: ADR-007 (two-table design that this decision depends on)
