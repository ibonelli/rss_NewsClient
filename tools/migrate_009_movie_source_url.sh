#!/usr/bin/env bash
# Idempotent migration: add movies.source_url — the RSS entry's own page link
# (e.g. the YTS movie page), now used as the Movies tab title link (M19).
# No data backfill is possible for existing rows: the original RSS <link> was
# never stored before this change (only used as a torrent_url fallback when
# an entry had no enclosure), so historical movies keep source_url = NULL
# until the ingester's normal merge/insert path fills it in on a future run
# (the feed re-lists the same movie, or a new quality variant arrives).
# Safe to re-run — skips the ALTER if the column already exists.
set -euo pipefail

DB_URL="${DATABASE_URL:-}"

if [ -z "$DB_URL" ]; then
    # Fall back to reading from config.yaml via python
    DB_URL=$(python - <<'EOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
cfg = load_config()
print(cfg["database"]["url"])
EOF
)
fi

echo "Applying migration 009 (movies.source_url) to: $DB_URL"

python - <<'EOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
from sqlalchemy import create_engine, text

cfg = load_config()
db_url = cfg["database"]["url"]
engine = create_engine(db_url)

with engine.connect() as conn:
    is_sqlite = db_url.startswith("sqlite")
    if is_sqlite:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(movies)")).fetchall()]
    else:
        cols = [row[0] for row in conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'movies'"
        )).fetchall()]

    if "source_url" not in cols:
        stmt = "ALTER TABLE movies ADD COLUMN source_url VARCHAR(1000)" if is_sqlite else "ALTER TABLE movies ADD COLUMN source_url VARCHAR(1000) NULL"
        conn.execute(text(stmt))
        conn.commit()
        print(f"Added source_url column ({'SQLite' if is_sqlite else 'MySQL'}).")
    else:
        print("source_url column already exists. Nothing to do.")
EOF
