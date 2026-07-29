# ADR-017: Saved Entries — one common cross-feed table, keyed by (source_type, source_id)

- **Status:** Accepted
- **Date:** 2026-07-28
- **Owners:** Self

## Context

The user wants a "Save Entry" action available on every item in every content tab — Movies, Series, News, Design — that copies a snapshot of the item into a dedicated store, separate from the source tables, browsable and exportable from a new "Saved" tab (mirroring the existing News export UX, ADR-009).

The four source tables have materially different shapes: `Movie` (title/year/genres/qualities/ratings/plot), `Series` (title/imdb_id/is_following/is_ignored — episode data lives in a separate `series_episodes` table), `NewsItem` (title/url/published_at/feed_name/full_content), `DesignItem` (title/url/published_at/feed_name/summary/image_url). None of them share a URL/date/summary field with identical semantics, and Series in particular has no single per-row "entry date" or "link" the way News/Design do — an episode-level date exists, but not a series-level one.

The user explicitly asked for "a different table with a common format... it can get saved from any type of feed," ruling out four separate per-type saved tables from the outset. This ADR records the resulting design questions: what the common schema looks like, what maps to each common field per source type, and how idempotency/dedup is enforced across four structurally different sources.

## Decision

1. **Single `saved_entries` table, common schema, no FK.** One table stores `source_type` (`movie`\|`series`\|`news`\|`design`), `source_id`, `title`, `link`, `entry_date` (nullable), `feed_name`, `summary`, and `saved_at`. There is no foreign key to any of the four source tables — a single FK column can't reference four different parent tables, so `source_id` validity is checked at the application layer, only at save time (FR-095, FR-096).
2. **Per-source-type field mapping, decided explicitly rather than left generic:**
   - **Movies:** `link` = the movie's IMDb URL (same value already computed for the title link, FR-038) rather than a torrent URL — durable webpage over a torrent file, and sidesteps "which quality variant" entirely. `entry_date` = `feed_entry_date`. `feed_name` = fixed `"Movies"`. `summary` = `plot` or `""`.
   - **Series:** saved at the **series-title level**, not per-episode — mirrors the existing Follow/Ignore action granularity (FR-054) and avoids the same "which quality variant" ambiguity a per-episode save would introduce. `link` = the series' IMDb URL (FR-045). `entry_date` = `Series.created_at`, since no single per-series feed date exists (dates live on `series_episodes`). `feed_name` = fixed `"Series"`. `summary` = `""` (no synopsis data exists for series).
   - **News / Design:** direct mapping from existing fields — `link`=`url`, `entry_date`=`published_at`, `feed_name`=the feed's own config name, `summary`=`full_content`/`summary` respectively.
3. **Idempotent on `(source_type, source_id)`, enforced by a unique index.** Re-clicking Save Entry on an already-saved item returns the existing row rather than inserting a duplicate (FR-097). This was chosen over keying on `(source_type, link)` — the frontend already holds the source row's id when rendering the button, so no extra URL-hashing step is needed, and it stays exact even if a source row's link were ever recomputed (e.g. a movie gaining an `imdb_id` after enrichment, changing its IMDb URL from title-search to a direct link).
4. **Every list endpoint gains an `is_saved` field.** `GET /api/movies`, `GET /api/series`, `GET /api/news/{feed}/items`, `GET /api/design/{feed}/items` each compute `is_saved` via a lookup against `saved_entries` by `(source_type, source_id)` (FR-098). Without this, the Save Entry button would only know an item was saved immediately after the click that saved it — reloading the page would show every button as unsaved regardless of prior saves, which contradicts the idempotent-button behavior the user asked for.
5. **No read/unread tracking on Saved; flat list + Remove only.** Unlike News/Design, `saved_entries` has no `is_read` column and no Mark Read/Unread UI. The only lifecycle action is "Remove from Saved" (`DELETE /api/saved/{id}`, FR-101) — a hard delete, not a soft flag. This keeps Saved intentionally lightweight: a bookmark list, not a sixth read-tracked content type.
6. **Export dumps everything, unlike the unread-only News export.** `GET /api/saved/export` (FR-102) returns every `saved_entries` row — there's no read state to filter by, and Remove already keeps the list from growing unbounded.

## Consequences

### Positive
- One schema, one API surface (`GET /api/saved`, `DELETE /api/saved/{id}`, `GET /api/saved/export`) for a feature that touches all four existing content types — no per-type Saved sub-view or per-type export needed
- Saving is a genuine snapshot/copy, not a live reference — a saved row is unaffected by later edits to (or hypothetical deletion of) its source row, which also means no cascade-delete logic is needed anywhere
- `is_saved` on every list response keeps the button state correct across reloads with a single indexed lookup per request, no extra round-trip from the frontend

### Negative
- `source_id` has no referential integrity at the database level — a bug that inserts a `saved_entries` row with a wrong `source_type`/`source_id` pair would go undetected by the schema; only application-layer validation at save time catches it (V-041)
- Four different, hand-picked field mappings (FR-096) mean "the common format" is common in shape only, not in meaning — `link` means "IMDb page" for two source types and "the article/torrent-page URL" for the other two; a future maintainer extending Saved needs to read FR-096 rather than infer the mapping from the column names alone
- Series saves the whole title, not a specific episode — if the user wanted to bookmark one particular episode (e.g. "the finale"), this granularity doesn't support that; revisiting would require a schema change (e.g. an optional `episode_id` alongside `source_id`)
- `entry_date` for Series (`created_at`, i.e. when the series was first discovered) is a materially different kind of date than `published_at`/`feed_entry_date` for the other three types (i.e. when the content itself was published) — a Saved-tab sort/display that treats `entry_date` uniformly will subtly mix "date discovered" and "date published" semantics for Series rows

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Four separate saved tables (`saved_movies`, `saved_series`, `saved_news`, `saved_design`), each with an FK to its source table | Real referential integrity per type; each row shape stays local to its type | Directly contradicts the user's explicit ask for "a different table with a common format"; Saved tab/export would need a 4-way UNION query and a merged response shape anyway | Rejected per explicit user instruction |
| Save per-episode for Series (matching the read-tracking granularity) | Consistent with episode-level Mark Read/Unread | No natural "link"/"date" at the episode level beyond a specific quality variant's torrent URL; conflicts with the existing series-level Follow/Ignore granularity the user is already used to | User chose per-series explicitly when asked |
| Key idempotency on `(source_type, link)` (hash-based, mirroring the existing `url_hash` pattern) | Decoupled from the source row's id; works even without holding an id client-side | Requires hashing/normalizing a URL that differs in kind per type (IMDb search URL vs. article URL); doesn't stay stable if a movie's IMDb link changes shape after enrichment | User chose `(source_type, source_id)` explicitly when asked |
| Give Saved its own read/unread tracking, matching News/Design | Full feature parity with existing content tabs | More moving parts (toggle, Mark Read/Unread, Mark All Read) for a feature meant to be a lightweight bookmark list; user wants a flat list, not a sixth tracked content type | User chose the flat-list option explicitly when asked |
| Saved export limited to unread entries (mirroring FR-033) | Consistent export semantics across the app | Saved has no read state to filter by under the flat-list decision; would need to invent a meaning for "unread" that doesn't otherwise exist in this feature | Moot once the flat-list decision was made; user confirmed export-everything |

## Links
- Related requirements: FR-095, FR-096, FR-097, FR-098, FR-099, FR-100, FR-101, FR-102, FR-103
- Related: ADR-009 (export/import pattern for News, reused here for Saved's export-only case), ADR-012 (Series title/episode split, informs why Series has no single per-row date), ADR-014 (per-feed-type URL routes, extended here with `/saved`)
