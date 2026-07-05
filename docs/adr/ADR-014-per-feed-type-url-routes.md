# ADR-014: Bookmarkable URL routes per feed type (client-side routed SPA)

- **Status:** Accepted
- **Date:** 2026-07-05
- **Owners:** Self

## Context

The web UI (ADR-004) is a single-page React app mounted at `/`. Navigation between Movies, Series, News, and Design was pure in-memory React state (`activeTab`) — the URL never changed. That meant the tabs (and any specific News/Design feed selected within them) could not be bookmarked, shared, or restored via browser back/forward, and refreshing the page always reset to the Movies tab.

The user asked for each feed type to have its own accessible URL, with News and Design additionally deep-linking to a specific configured sub-feed (e.g. a single news source or design blog).

## Decision

Add one URL per feed type, using client-side routing on top of the existing no-build-step React setup:

1. **FastAPI routes** (`src/webui/routes.py`): `/movies`, `/series`, `/news`, `/news/{feed_name}`, `/design`, `/design/{feed_name}` are all registered on a single handler (`serve_spa_route`) that returns the same `index.html` shell already served at `/`. The server does no per-route rendering or data lookup — `feed_name` is accepted but unused server-side.
2. **Client-side router** (`src/webui/static/app.js`): a small router built on the browser History API — `parseLocation()` reads `window.location.pathname` to derive `{ tab, feedName }` (falling back to `movies` for unknown paths), `navigate()` pushes a new URL via `history.pushState`, `replaceLocation()` swaps the URL without adding a history entry (used to reflect the feed that gets auto-selected on load), and a `popstate` listener keeps state in sync with browser back/forward.
3. Tab buttons call `navigate("/<tab>")`; selecting a feed inside the News or Design tab calls `navigate("/news/<feed>")` / `navigate("/design/<feed>")`.

## Consequences

### Positive
- Every feed type (and specific News/Design feed) is bookmarkable and shareable as a plain URL
- Browser back/forward and refresh now behave as users expect from a normal multi-page site
- No server-side templating, session state, or per-route data fetching added — the backend change is a single trivial handler reused six times
- No new frontend dependencies; consistent with ADR-004's no-build-step constraint

### Negative
- Routing logic (path parsing, history sync) is hand-rolled rather than using a routing library — acceptable at this scale (4 tabs, 2 with sub-feeds) but would need revisiting if navigation depth grows further
- `feed_name` in the URL is a raw, URL-encoded config `name` value, not a stable slug/ID — renaming a feed in `config.yaml` breaks previously bookmarked links (no redirect/alias mechanism)

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Keep tab state only, no URL routing | Zero effort | Not bookmarkable/shareable; back/forward does nothing; refresh always resets to Movies | Doesn't meet the request |
| Pull in a routing library (e.g. a CDN build of a router) | Handles edge cases (nested routes, redirects) | New CDN dependency; more machinery than 6 flat routes need | Over-engineered for this app's navigation depth |
| Server-side rendering per route (return different HTML per tab) | "Real" server routing | Reintroduces server templating that ADR-004 deliberately removed; still needs client JS for read/enrich actions | Contradicts ADR-004 |

## Links
- Related requirements: FR-075, FR-076, FR-077
- Supersedes/extends: ADR-004 (frontend remains React-via-CDN; this only adds routing on top)
