# ADR-010: Series IMDb link derived from feed-provided IMDb ID, no external lookup

- **Status:** Accepted
- **Date:** 2026-06-20
- **Owners:** Ignacio Bonelli

## Context

The Series tab must display a link to the IMDb page for each series (FR-045). Two approaches exist: parse the IMDb ID from the EZTV RSS feed entry and construct the URL client-side, or perform an external lookup (e.g., TVDb, OMDb) at ingestion time to resolve the IMDb ID from the series title. EZTV RSS entries include an IMDb ID element per entry (exact field name subject to live inspection — Q-009, Q-011). Using this field avoids any external API call for series metadata, consistent with C-009.

## Decision

Store the IMDb ID parsed directly from the EZTV RSS feed entry into the `series.imdb_id` column. The Web UI constructs the IMDb URL as `https://www.imdb.com/title/{imdb_id}/` at render time. When `imdb_id` is null (absent from the feed entry), no link is shown.

## Consequences

### Positive
- No external API call required for series metadata — consistent with C-009 and the zero-cost constraint
- IMDb ID is available immediately at ingestion time with no enrichment step
- Implementation is simple: one field extracted, one URL template in the frontend

### Negative
- IMDb ID accuracy depends entirely on EZTV — if their feed carries an incorrect or missing ID, the app has no fallback
- No IMDb link for entries where the feed omits the IMDb ID (stored as null)
- If EZTV changes the XML element name for the IMDb ID, the parser must be updated

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Look up IMDb ID via TVDb or OMDb at ingestion | Reliable ID even if EZTV omits it | Requires external API call; TVDb requires auth; OMDb free tier has rate limits; violates C-009 spirit | Rejected — adds complexity and potential cost for a marginal reliability gain |
| Store full IMDb URL instead of ID | Slightly simpler frontend | URL is derivable from ID; storing redundant data | Rejected — storing the ID is cleaner and keeps the URL template in one place |
| Search IMDb directly at render time | Always fresh | Requires scraping or paid API per page load; far too expensive | Rejected — not feasible |

## Links
- Related requirements: FR-040, FR-045, C-009
- Related design docs: `docs/03-architecture-data/Data-Contracts.md` (Series model, V-026)
- Open question resolved (partially): Q-011 (IMDb ID is per-entry in the feed; stored at the series row level)
