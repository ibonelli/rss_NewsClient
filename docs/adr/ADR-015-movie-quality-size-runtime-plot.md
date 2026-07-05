# ADR-015: Fix genre-fusion parsing bug; add Size (per-quality), Runtime, Plot

- **Status:** Accepted
- **Date:** 2026-07-05
- **Owners:** Self

## Context

`_DescriptionParser` (`src/cli/fetcher.py`) flattens the entire RSS `<description>` HTML into one space-joined text blob, destroying all line-break/tag structure. The genre regex terminated only on a literal `Rating:` substring or end-of-string:

```python
genre_match = re.search(r"Genre:\s*(.+?)(?:\n|$|Rating:)", full_text, re.IGNORECASE)
```

The real YTS description layout is `IMDB Rating → Genre → Size → Runtime → plot synopsis` — `Rating:` always appears *before* `Genre:`, so the terminator never matched again, and the capture ran to end-of-string, fusing the last genre together with `Size:`, `Runtime:`, and the entire plot synopsis into one garbage token (reported live example: movie "Crime 101" — `genres[3] == "Thriller Size: 1.26 GB Runtime: 2hr 20 min A meticulous jewel thief risks..."`).

Auditing the existing database confirmed this wasn't a one-off: **30 of 40** already-ingested movies had this corruption. There was also no extraction at all for Size, Runtime, or plot — none of that data was being captured.

## Decision

1. **Fix the genre regex** to bound on a lookahead over every label that can actually follow it (`Size:`, `Runtime:`, `Rating:`, or end-of-string) instead of a single literal terminator.
2. **Add Size/Runtime/Plot extraction**, each bounded by its own value shape (`Size`/`Runtime`) or by "whatever follows the last recognized label" (`Plot`), rather than depending on a specific label always being present.
3. **Size is a property of the quality/format, not a separate genre or a flat movie field.** `Movie.qualities` changes shape from a flat list of strings (`["1080p"]`) to a list of `{"quality": "1080p", "size": "1.26 GB"}` objects — deliberately mirroring the pattern already used for `SeriesEpisode.qualities` (`[{"quality": ..., "torrent_page_url": ...}]`), including its merge-by-quality-key dedup logic.
4. **`runtime`** is stored as-is (raw string, e.g. `"2hr 20 min"`) — not normalized to minutes, since the source format is inconsistent and unnormalized text is sufficient for display.
5. **`plot`** is a new nullable `Text` column holding the full, untruncated synopsis.
6. **Existing corrupted data is repaired, not just prevented going forward.** The original Size/Runtime/plot text is still fully recoverable from what was stored (the corruption was a mis-split, not data loss), so the migration script reconstructs and repairs `genres`/`runtime`/`plot` for every already-affected row in addition to adding the new columns and backfilling the `qualities` shape.

## Consequences

### Positive
- The exact reported bug is fixed and covered by a regression test (`tests/test_fetcher.py`) using the real "Crime 101" description as a fixture.
- Existing corrupted rows are repaired in place — the user doesn't have to wait for a future re-ingest (which wouldn't have fixed genres anyway, since genres were never re-merged on duplicate match) or manually edit the database.
- Size/Runtime/Plot are now genuinely captured and surfaced in the UI, not silently discarded.
- `qualities` shape change follows an established precedent (`SeriesEpisode`), keeping the codebase consistent rather than inventing a new convention.

### Negative
- `Movie.qualities` is now a breaking shape change for any external consumer of `GET /api/movies` — mitigated since this is a single-user personal app with one first-party frontend, updated in the same change.
- Size is only known for whichever quality variant was recorded in the *first* insert's description; qualities merged in later via dedup keep `size: null` (matches the existing "don't update on match" precedent for series qualities) — a movie with multiple quality variants will show sizes for at most one of them until each variant happens to be the first-seen one.
- Runtime format coverage is limited to the two observed patterns (`"Xhr Y min"`, `"NN min"`); an unseen format would fail soft (`runtime: null`) rather than crash, but wouldn't be captured either.

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Only fix the genre regex, skip Size/Runtime/Plot | Minimal, addresses just the reported symptom | Leaves the underlying description data (already being scraped and discarded) unused; user explicitly asked for these to become real fields | User wanted the full data captured |
| Store `size` as a flat `Movie.size` column | Simpler schema (no shape change to `qualities`) | Wrong semantically — size varies per quality/format, a flat field would only ever reflect one variant misleadingly labeled as "the" size | User explicitly identified size as a per-format property |
| Normalize `runtime` to integer minutes | More useful for future sorting/filtering | Adds parsing complexity for inconsistent source formats or ones not yet been seen; no current feature needs numeric runtime | Store as-is is simpler and sufficient for display |
| Leave existing corrupted rows uncorrected (fix only applies going forward) | Simpler migration, no data-repair logic | The user's own reported example remains broken in their live database indefinitely; 75% of existing movies were affected | Original data was recoverable — leaving it broken would defeat the point of the fix |

## Links
- Related requirements: FR-078, FR-079, FR-080
- Related migration: `tools/migrate_004_movie_runtime_plot.sh`
- Related tests: `tests/test_fetcher.py`
