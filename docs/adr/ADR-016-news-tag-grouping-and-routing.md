# ADR-016: News feeds grouped by tag into two-level tabs; URL scheme extended to /news/{tag}/{feed_name}

- **Status:** Accepted
- **Date:** 2026-07-21
- **Owners:** Self

## Context

The News tab (ADR-014) renders a single flat row of feed-picker buttons, one per `news_feeds` config entry. As more feeds get added, that flat list doesn't scale — there's no way to group related feeds (e.g. all tech feeds, all security feeds) so the user can jump between groups instead of scanning every feed name.

The user asked for each `news_feeds` entry to carry a `tag`, with the News tab organizing feeds into tag tabs, each tab containing the feeds for that tag.

This directly interacts with ADR-014's bookmarkable-URL scheme (`/news/{feed_name}`), which that ADR already flagged as fragile: *"`feed_name` in the URL is a raw, URL-encoded config `name` value, not a stable slug/ID — renaming a feed in `config.yaml` breaks previously bookmarked links."* Adding a grouping level forces a decision on whether/how the URL scheme changes too.

## Decision

1. **Tag is single-valued, config-only.** Each `news_feeds` entry gets one `tag: string` field. A feed without `tag` falls back to a default `"General"` tag. `tag` is never persisted on `news_items` or any DB row — it's read from `config.yaml` at request time, the same treatment as the existing `type`/`filters` fields (FR-090).
2. **Tab order is explicit, not derived.** A new `news_tag_priority` ordered list (mirroring the existing `genre_priority` for movies) controls tag-tab order. Any tag used by a feed but missing from that list still gets a tab — appended after the ordered ones, in first-appearance order — so a forgotten config update never hides a feed (FR-091).
3. **Two-level UI.** The News tab renders tag tabs above the existing per-feed picker, the latter scoped to the active tag's feeds. Switching tag auto-selects the first feed under it, mirroring the current auto-select-first-feed behavior (FR-092). Each tag tab shows an aggregate unread badge — the sum of its feeds' unread counts (FR-093).
4. **URL scheme grows by one segment, with an intentional break.** The News deep-link route becomes `/news/{tag}/{feed_name}` (and `/news/{tag}` for tag-only). The prior two-segment `/news/{feed_name}` form is retired outright — **no redirect or alias is provided**. Visiting an old-style link (or any unrecognized News path) falls back to the News tab's own default (first tag, first feed), the same fallback behavior FR-077 already defines for unrecognized paths generally (FR-094). This is a deliberate acceptance of ADR-014's flagged fragility rather than an attempt to solve it: for a single-user local app, a stale bookmark landing on a sensible default is cheaper than building and maintaining alias/redirect logic. `design_feeds` and `/design/{feed_name}` are untouched — this ADR applies to News only.

## Consequences

### Positive
- Feed grouping is entirely config-driven, matching the existing `genre_priority`/`type`/`filters` pattern — no DB migration, no new table
- Tab order is explicit and typo-tolerant (unlisted tags still surface, never silently dropped)
- The server does all the sorting once (`GET /api/news` returns feeds pre-grouped in tag-priority order); the client only needs to group the already-ordered array by `tag` — no second endpoint or config exposed to the frontend

### Negative
- Any bookmark or shared link using the old `/news/{feed_name}` form breaks — it silently falls back to the News tab default instead of the originally intended feed, with no warning to the user that the link was stale
- Renaming a feed's `tag` in config changes its tab position/grouping and its bookmarkable URL simultaneously, compounding ADR-014's existing `feed_name`-rename fragility
- Two config lists now govern News feed presentation (`news_tag_priority` for tab order, `news_feeds[].tag` for grouping) — one more thing to keep in sync when adding a feed

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Keep `/news/{feed_name}` unchanged; derive the active tag tab server/client-side by looking up the feed's tag | No broken bookmarks, no route change | Doesn't let a bare tag-only URL (`/news/{tag}`) exist as its own bookmarkable state | Rejected after weighing the tradeoff — chose the explicit three-segment scheme for a cleaner, symmetric URL structure, accepting the break |
| Alphabetical or config-declaration-order tab ordering (no `news_tag_priority`) | Zero new config | No control over tab order (e.g. can't put "Tech" before "Security" independent of where feeds are declared) | User wanted explicit control, mirroring `genre_priority` |
| Best-effort redirect from old `/news/{feed_name}` to the new tag-scoped path | Preserves old bookmarks | Extra lookup/redirect logic for a single-user local app with low link-sharing surface | Explicitly declined — not worth the complexity here |
| Allow multiple tags per feed (list-valued) | More flexible grouping | More complex config, API shape, and active-tab-lookup logic for marginal benefit at this app's scale | User confirmed single-tag-per-feed is sufficient |

## Links
- Related requirements: FR-090, FR-091, FR-092, FR-093, FR-094
- Supersedes/extends: ADR-014 (News-only; Design's `/design/{feed_name}` scheme is unchanged)
