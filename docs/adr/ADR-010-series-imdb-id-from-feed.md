# ADR-010: Series IMDb link via title search URL; no IMDb ID in EZTV feed

- **Status:** Accepted
- **Date:** 2026-06-20
- **Owners:** Ignacio Bonelli

## Context

The Series tab must display a link to the IMDb page for each series (FR-045). The original assumption (pre-implementation) was that the EZTV RSS feed would include an IMDb ID element per entry. Live feed inspection (Q-009, Q-011) showed this is not the case — the EZTV feed provides no IMDb ID. The `series.imdb_id` column exists but is always null in practice. Three options remain: leave no link, construct an IMDb title-search URL from the series name, or perform an external lookup at ingestion time.

## Decision

Construct an IMDb title-search URL from the series name at render time: `https://www.imdb.com/search/title/?title={title}&title_type=tv_series`. The `series.imdb_id` column is retained (nullable) in case a future feed source provides it. When `imdb_id` is present, the UI uses the direct URL `https://www.imdb.com/title/{imdb_id}/` instead.

## Consequences

### Positive
- No external API call required for series metadata — consistent with C-009 and the zero-cost constraint
- IMDb ID is available immediately at ingestion time with no enrichment step
- Implementation is simple: one field extracted, one URL template in the frontend

### Negative
- Search URL lands on an IMDb results page, not a direct series page — one extra click for the user
- If a series title is ambiguous, the search may not surface the right result first
- `series.imdb_id` column is permanently null unless the feed or a future enrichment step populates it

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| No IMDb link at all | Simplest | Loses the feature entirely | Rejected — even a search URL is useful |
| Look up IMDb ID via TVDb or OMDb at ingestion | Direct link, no ambiguity | External API call per series; TVDb requires auth; OMDb rate-limited; violates C-009 spirit | Rejected — adds complexity and potential cost |
| Store full IMDb search URL instead of ID | Slightly simpler frontend | URL is derivable from title; storing redundant data | Rejected — constructing it at render time is cleaner |

## Links
- Related requirements: FR-040, FR-045, C-009
- Related design docs: `docs/03-architecture-data/Data-Contracts.md` (Series model, V-026)
- Open question resolved (partially): Q-011 (IMDb ID is per-entry in the feed; stored at the series row level)
