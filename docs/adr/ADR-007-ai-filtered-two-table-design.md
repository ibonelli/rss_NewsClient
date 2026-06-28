# ADR-007: Two-table design for AI-filtered news (news_items + ai_filtered_views)

- **Status:** Superseded by M10 — `ai_filtered` feed type removed; `ai_filtered_views` table retained in DB but no longer used
- **Date:** 2026-06-15
- **Owners:** Ignacio Bonelli

## Context

AI-filtered feeds require storing two distinct things: the raw fetched item (needed for the unprocessed sub-view in FR-032, and as the input for re-processing unread items) and the AI-processed result (category, summary, tags, read status, keep_as_context flag). These have different lifecycles — a raw item is written once by the Ingester and never changes; an AI-filtered view row is written or updated by the Filter Processor each cycle for unread items. Merging them into one table produces nullable columns for all AI fields on raw items and creates ambiguous read-tracking semantics (is `is_read` tracking the raw item or the AI result?).

## Decision

Use two tables: `news_items` stores all raw fetched items for all feed types (including AI-filtered); `ai_filtered_views` stores the AI-processed results for items Claude chose to include. Presence of a row in `ai_filtered_views` indicates Claude included the item; absence means it is either pending processing or was not returned by Claude in any run.

## Consequences

### Positive
- Clean lifecycle separation: Ingester writes `news_items`, Filter Processor writes `ai_filtered_views`
- Re-processing logic is unambiguous: items with no `ai_filtered_views` row (pending) and items with `is_read = false` (unread, re-evaluate) are the processing targets
- Raw sub-view (FR-032) reads `news_items` directly with no additional logic
- `keep_as_context` and `last_filtered_at` are naturally scoped to the AI view, not the raw item

### Negative
- JOIN required to cross-reference raw items with their AI-processed state
- Two tables to keep consistent; deleting a `news_items` row must cascade to `ai_filtered_views`

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Single table with nullable AI columns | Simpler schema; no JOIN | Ambiguous read-tracking (raw vs. AI view); `keep_as_context` semantics unclear on raw items; messy re-processing queries | Rejected — semantic ambiguity grows as AI fields expand |
| Separate table per feed type | Maximum isolation | Over-engineered; duplicates `news_items` structure for each type; harder to query across feeds | Rejected — unnecessary complexity for a personal project |

## Links
- Related requirements: FR-026, FR-027, FR-031, FR-032
- Related design docs: `docs/02-planning/High-Level-Design.md`
