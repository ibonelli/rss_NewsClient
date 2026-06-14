# ADR-003: On-demand enrichment triggered by user

- **Status:** Accepted
- **Date:** 2026-05-21
- **Owners:** Self

## Context

The original requirements (FR-009 through FR-012) specified automatic enrichment during ingestion — the CLI ingester would fetch IMDb and Rotten Tomatoes ratings from external APIs for every new movie as part of the ingestion pipeline. This creates coupling between ingestion reliability and external API availability, adds latency to the ingestion process, and may hit rate limits on free API tiers. Additionally, the YTS RSS feed itself may already include some rating data (e.g., IMDb rating in the description HTML) that can be extracted without external calls.

## Decision

Enrichment is split into two modes:
1. **Passive extraction at ingestion:** Parse any ratings already present in the RSS feed data (no external API calls).
2. **On-demand enrichment via web UI:** User clicks a per-movie "refresh ratings" button in the FastAPI web app, which triggers an external API call to fetch/update ratings for that specific movie.

Automatic bulk enrichment during ingestion is removed.

## Consequences

### Positive
- Ingestion is faster and more reliable (no external API dependency)
- No risk of hitting rate limits during bulk ingestion
- User controls when and which movies get enriched (only movies they care about)
- Simpler error handling — enrichment failures are visible to the user immediately
- RSS-native ratings (if present) are available instantly without external calls

### Negative
- Movies without RSS-native ratings will show "no rating" until user manually enriches
- User must actively click to enrich — slight friction vs. automatic
- If user wants to enrich many movies at once, must click each one individually (no bulk action currently planned)

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Automatic enrichment during ingestion | All movies have ratings; no user action needed | Slow ingestion; API failures block pipeline; rate limit risk | Couples ingestion to external API availability |
| Separate scheduled enrichment step | Decouples ingestion from enrichment; background processing | Still hits rate limits; enriches movies user may never look at | Wastes API calls on movies user doesn't care about |
| Lazy enrichment on first view | No wasted calls; transparent to user | Slow page loads; complex async rendering | Poor UX (loading spinners on every card) |

## Links
- Related requirements: FR-009, FR-010, FR-011, FR-012, NFR-004
- Related design docs: `docs/03-architecture-data/Architecture-Overview.md` (Section 2, Web App Routes)
