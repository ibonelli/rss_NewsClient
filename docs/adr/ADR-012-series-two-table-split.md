# ADR-012: Series data split into `series` and `series_episodes` tables

- **Status:** Accepted
- **Date:** 2026-06-26
- **Owners:** Ignacio Bonelli

## Context

The original `series` table stored one row per unique `(title, season, episode)` combination, making it analogous to the `movies` table. When the Ignore feature was designed (M7), the requirement was to ignore at the **series title level** — hiding all episodes of a show at once. Implementing this on the single-table design required either:

1. Storing `is_ignored` on every episode row and updating all of them in bulk every time ignore/unignore is toggled, or
2. Querying by title string for every ignore operation (no clean FK relationship).

Neither option has a natural primary key for the ignore endpoint, and both create denormalization pressure: `is_ignored` is a series-level attribute but would have to be repeated on every episode row.

Additionally, `imdb_id` and any future series-level metadata (e.g., a poster URL, a user note) logically belong to the series title, not to each individual episode.

## Decision

Split into two tables:

**`series`** — one row per unique series title:
- `id` (PK), `title` (UNIQUE), `imdb_id` (nullable), `is_ignored` (bool, default false), `created_at`, `updated_at`

**`series_episodes`** — one row per unique `(series_id, season, episode)`:
- `id` (PK), `series_id` (FK → series.id), `season`, `episode`, `qualities` (JSON), `feed_entry_date`, `ingested_at`, `is_read` (bool), `created_at`, `updated_at`

`is_ignored` lives exclusively on the `series` row. `is_read` lives exclusively on the `series_episodes` row. Quality variants remain as a JSON array on the episode row (ADR-011 preserved).

Ignore/unignore endpoints operate on the `series.id` PK. No bulk episode-row update is needed — a join on `is_ignored` at query time is sufficient.

## Consequences

### Positive
- `is_ignored` has a natural home and a clean PK for API operations
- Series-level metadata (`imdb_id`, future fields) is stored once, not repeated per episode
- Dedup logic is cleaner: upsert series title first, then upsert episode — no full `(title, season, episode)` compound key to manage in a single table
- Ignore/unignore is O(1) (single row update on `series`)

### Negative
- `GET /api/series` requires a JOIN between `series` and `series_episodes`
- Ingester deduplication becomes two-step (check/insert series row, then check/insert episode row)
- Existing `series` table data is not migrated — `clear_db.sh` must be run before deploying M7

### Migration
No migration script. The database is cleared with `clear_db.sh` and repopulated by the next ingester run. Acceptable because the `series` data is fully derivable from the live EZTV feed.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| Keep single table; add `is_ignored` per episode row | No schema split | Updating all episodes on ignore/unignore; `is_ignored` semantically wrong at episode level | Rejected — poor semantic fit |
| Keep single table; ignore by title string (no PK) | No schema split | No clean FK; URL-encoding titles in API paths; race condition if title changes | Rejected — fragile API design |
| Three tables: series + seasons + episodes | Fully normalized | Unnecessary complexity; seasons have no independent metadata | Rejected — over-engineered for current needs |

## Links
- Related requirements: FR-041, FR-042, FR-051, FR-052, FR-053
- Supersedes: single-table `series` design from M6
- Related: ADR-011 (qualities as JSON on episode row — preserved)
