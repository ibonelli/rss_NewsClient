# ADR-004: Replace Jinja2 + HTMX with React via CDN

- **Status:** Accepted
- **Date:** 2026-05-28
- **Owners:** Self
- **Supersedes:** ADR-001 (partially — keeps FastAPI decision, replaces Jinja2/HTMX rendering approach)

## Context

ADR-001 chose FastAPI + Jinja2 + HTMX for the web layer, rejecting a React SPA as "over-engineered." However, the user now prefers a React-based frontend for richer client-side interactivity. By loading React via CDN (no build step, no Node.js tooling), the complexity concern is mitigated — there is no separate build pipeline, no `node_modules`, and no bundler configuration. The FastAPI backend remains but shifts from rendering HTML to serving a JSON API.

## Decision

Replace Jinja2 server-rendered templates and HTMX with:

1. **React 18** loaded via CDN (`<script>` tags) — no build step required
2. **Babel Standalone** via CDN for in-browser JSX transformation
3. **FastAPI JSON API** — all data endpoints return JSON instead of HTML
4. **FastAPI static file serving** — serves `index.html`, `app.js`, `styles.css` from a `static/` directory
5. **Single process** — FastAPI serves both the static frontend and the API (no separate web server)

The frontend is a static HTML page with an embedded React application that fetches data from the API and renders the movie list, handling read-tracking and enrichment triggers client-side.

## Consequences

### Positive
- Richer client-side interactivity without full page reloads
- Clean separation between API (data) and presentation (React components)
- No build step — React and Babel loaded from CDN, components written in plain `.js` files
- Still a single Python process (`pelis serve`) — no additional infrastructure
- JSON API makes future alternative frontends trivial (mobile app, CLI consumer, etc.)

### Negative
- Requires internet connectivity to load React/Babel from CDN on first page load (can be cached)
- In-browser JSX transform (Babel Standalone) adds ~1s to initial load — acceptable for personal project
- Slightly larger initial payload than server-rendered HTML (React library ~40KB gzipped)
- Debugging JSX errors is less clear than with a proper build step

### Mitigations
- CDN libraries are cached aggressively by the browser after first load
- For offline use, CDN scripts could be vendored into the `static/` directory as a future enhancement
- Browser DevTools React extension provides debugging support

## Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Keep Jinja2 + HTMX | Already designed, simpler | User preference for React; less flexible for future enhancements | User decision to switch |
| React with Vite build step | Proper tooling, better DX, tree-shaking | Adds Node.js dependency, `npm install`, build pipeline | Over-engineered for personal project without build system |
| Preact via CDN | Smaller bundle (3KB) | Less ecosystem support, fewer examples | React is well-known and CDN size is acceptable |
| Vanilla JS (no framework) | Zero dependencies | Manual DOM manipulation, harder to maintain as UI grows | React provides better component model |

## Links
- Supersedes: ADR-001 (rendering approach only — FastAPI choice remains valid)
- Related requirements: FR-004, FR-017, FR-018, C-006
- Related docs: `docs/03-architecture-data/Architecture-Overview.md`
