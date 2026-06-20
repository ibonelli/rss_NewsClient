# ADR-011: Series quality variants stored as denormalized JSON array on the series row

- **Status:** Accepted
- **Date:** 2026-06-20
- **Owners:** Ignacio Bonelli

## Context

Each series episode (identified by `title + season + episode`) may appear in multiple quality variants (e.g., 720p, 1080p), each with its own torrent page URL. The data model must represent these variants without creating duplicate rows per episode. Two structural options exist: a denormalized JSON column on the `series` row (same pattern used by `movies.qualities`), or a normalized child table (`series_qualities`) with a FK to `series`.

## Decision

Store quality variants as a JSON array in `series.qualities`, where each element is `{"quality": "720p", "torrent_page_url": "https://..."}`. This mirrors the existing `movies.qualities` pattern and keeps each episode as a single database row.

## Consequences

### Positive
- Consistent with the existing `Movie` model — same deduplication and merge logic can be reused or adapted
- Single row per episode simplifies read-tracking (one `is_read` flag per episode, not per quality)
- No join required to retrieve all qualities for an episode — simpler queries
- Adding a new quality variant is an in-place JSON merge, not an INSERT into a child table

### Negative
- Cannot index or query individual quality values in SQL without JSON functions (not needed for current use cases)
- Merging quality variants requires deserializing, deduplicating, and re-serializing JSON in Python on every ingestion run
- Schema of the JSON objects is implicit — no DB-level enforcement of `quality` and `torrent_page_url` fields (enforced by V-024 in application code instead)

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Normalized `series_qualities` child table | SQL-queryable per quality; enforced schema | Join required on every read; separate INSERT per variant; complicates dedup merge; over-engineered for a personal project | Rejected — complexity outweighs benefit given no SQL-level quality filtering is needed |
| One `series` row per quality variant | Simplest ingestion | Breaks the "one row per episode" model; read-tracking becomes per-quality rather than per-episode; duplicates series/season/episode metadata | Rejected — contradicts FR-041 and makes the UI grouping logic far more complex |

## Links
- Related requirements: FR-041, FR-045
- Related design docs: `docs/03-architecture-data/Data-Contracts.md` (Series model, V-024, V-025)
- Related ADR: ADR-007 (same JSON-column pattern established for movies)
