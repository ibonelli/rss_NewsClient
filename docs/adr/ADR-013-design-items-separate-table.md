# ADR-013 — Separate `design_items` table for Design Feed

**Date:** 2026-06-29
**Status:** Accepted

## Context

M11 introduces a Design Feed — a new content type that fetches articles from design RSS feeds (e.g., Designboom) and displays them as image+title+summary cards. The question was whether to store these items in the existing `news_items` table or in a new dedicated table.

Two options considered:

**Option A — Reuse `news_items`**
Add an `image_url` column to `news_items` and differentiate design items by feed name or a new `content_type` column. Avoids a new table and migration.

**Option B — New `design_items` table**
Create a dedicated table with `image_url` as a first-class column. Follows the same pattern as `movies` vs `news_items`.

## Decision

**Option B — New `design_items` table.**

## Rationale

- `image_url` is core to the design feed's identity; adding it to `news_items` would leave it null for every existing news row and conflate two unrelated content types.
- Design items have no `matched_filter_id`, no filter workflow, and no export — keeping them separate avoids null columns and dead logic paths on the news side.
- `news_items` already has its own query paths, export endpoint, and filter processor integration; sharing the table would complicate all three.
- `create_all()` adds the new table non-destructively on startup — no manual migration needed on existing installations.

## Consequences

- A new `DesignItem` SQLAlchemy model is added to `src/common/models.py`.
- `config.py` gains a `design_feeds` list (parallel to `news_feeds`).
- The Ingester, routes, and frontend each gain a separate design code path.
- Existing `news_items` rows and the Filter Processor are completely unaffected.
