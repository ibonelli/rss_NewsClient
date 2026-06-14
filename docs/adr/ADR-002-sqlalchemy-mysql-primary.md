# ADR-002: Database abstraction via SQLAlchemy with MySQL as primary backend

- **Status:** Accepted
- **Date:** 2026-05-21
- **Owners:** Self

## Context

Constraint C-002 requires support for both SQLite and MySQL. The original scoping (Phase 0) treated SQLite as the primary backend with MySQL as an optional alternative. After further consideration, MySQL should be the primary target (used when a server is available), with SQLite as the fallback for simpler setups. Supporting two databases requires a consistent abstraction layer to avoid writing backend-specific SQL and doubling the testing surface.

## Decision

Use SQLAlchemy (ORM mode) as the database abstraction layer. MySQL is the primary supported backend; SQLite is the secondary/fallback backend. The connection string in the config file determines which backend is used at runtime. No raw SQL — all queries go through SQLAlchemy models and query API.

## Consequences

### Positive
- Single codebase handles both backends transparently
- SQLAlchemy handles dialect differences (e.g., auto-increment, datetime handling)
- Models are shared between CLI ingester and FastAPI web app
- Migrations can be managed with Alembic if schema evolves
- Well-tested, mature library with strong community support

### Negative
- Adds SQLAlchemy as a dependency (plus mysqlclient or PyMySQL for MySQL driver)
- Some performance overhead vs. raw SQL (negligible for this scale)
- Must avoid backend-specific features (e.g., MySQL full-text search) unless properly abstracted
- SQLite has limited concurrent write support — acceptable since only the ingester writes

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|-------------|
| Raw SQL with if/else per backend | No ORM dependency, full control | Double maintenance, easy to introduce dialect bugs | Too error-prone for dual-backend |
| Peewee ORM | Lightweight, simpler API | Less mature async support, smaller ecosystem | SQLAlchemy is more widely used and better documented |
| Tortoise ORM | Async-native, Django-like | Less mature, smaller community | Risk of maintenance abandonment |
| SQLite only (drop MySQL) | Simplest possible | Violates C-002; limits future scalability | Constraint violation |

## Links
- Related requirements: FR-002, C-002
- Related design docs: `docs/02-planning/High-Level-Design.md`
