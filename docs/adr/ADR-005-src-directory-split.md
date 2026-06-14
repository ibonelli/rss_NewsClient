# ADR-005: Replace unified `pelis/` package with `src/cli/` + `src/webui/` + `src/common/` structure

- **Status:** Accepted
- **Date:** 2026-05-29
- **Owners:** Self

## Context

The Architecture Overview (Phase 3) proposed a single `pelis/` Python package with submodules (`ingester/`, `enrichment/`, `webapp/`) and a unified CLI entry point via Click (`pelis ingest`, `pelis serve`). During execution, a different structure emerged: the ingester and the web app are fundamentally independent applications that share only the data layer (models, DB setup, config). A unified CLI package adds coupling (shared versioning, single install) without clear benefit for two processes that never run together. Additionally, the ingester concept is generic — it could work with non-movie feeds in the future — and shouldn't be tied to a movie-specific package name.

## Decision

Organize the project as three top-level source directories under `src/`:

1. `src/cli/` — The ingestion process (entry point: `python src/cli/main.py`)
2. `src/webui/` — The FastAPI web application (entry point: `python src/webui/main.py`)
3. `src/common/` — Shared components (SQLAlchemy models, DB session, config loading)

Each process has its own `main.py` entry point. No Click-based unified CLI. No installable package.

## Consequences

### Positive
- Clear physical separation between the two independent processes
- Each process can evolve independently (different dependencies in the future if needed)
- `src/common/` makes the shared contract explicit — no hidden coupling
- Simpler invocation: `python src/cli/main.py` and `python src/webui/main.py` — no package install step required
- Ingester naming is generic, not tied to "pelis"

### Negative
- No `pip install -e .` convenience — must run from project root or manage PYTHONPATH
- No unified version number across components (acceptable for personal project)
- Slightly more verbose invocation than `pelis ingest`

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Unified `pelis/` package (original proposal) | Single install, clean CLI (`pelis ingest`/`pelis serve`), conventional Python packaging | Couples two independent processes, requires Click + setup.py/pyproject.toml, package name ties to movie domain | Over-packaging for a personal project with two independent scripts |
| Monorepo with separate `packages/cli/` and `packages/webui/` | Full isolation, independent packaging | Overkill for a local project with shared models | Unnecessary complexity |
| Single flat directory with `ingest.py` and `serve.py` | Simplest possible | Shared code would need duplication or awkward imports | Doesn't scale even slightly |

## Links
- Related constraints: C-003 (two separate processes)
- Related design docs: `docs/03-architecture-data/Architecture-Overview.md` (Section 1 — project structure)
- Related execution docs: `docs/04-execution/Implementation-Notes.md`
