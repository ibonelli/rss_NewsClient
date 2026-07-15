#!/usr/bin/env bash
# Idempotent migration: add is_following column to the series table.
# Existing rows (all currently is_ignored=false or is_ignored=true) get
# is_following=0 by default — non-ignored series move to Inbox, not Following,
# since "Following" is now an explicit opt-in (see ADR for the Inbox/Following/Ignored model).
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

echo "Applying migration 005 (series.is_following) to: $DB_URL"

python - <<EOF
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
from sqlalchemy import create_engine, text

cfg = load_config()
engine = create_engine(cfg["database"]["url"])

with engine.connect() as conn:
    if cfg["database"]["url"].startswith("sqlite"):
        result = conn.execute(text("PRAGMA table_info(series)")).fetchall()
        col_names = [row[1] for row in result]
        if "is_following" not in col_names:
            conn.execute(text("ALTER TABLE series ADD COLUMN is_following BOOLEAN NOT NULL DEFAULT 0"))
            conn.commit()
            print("Added is_following column (SQLite).")
        else:
            print("is_following column already exists (SQLite). Nothing to do.")
    else:
        # MySQL: check information_schema
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'series' AND COLUMN_NAME = 'is_following'"
        )).scalar()
        if result == 0:
            conn.execute(text("ALTER TABLE series ADD COLUMN is_following BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.commit()
            print("Added is_following column (MySQL).")
        else:
            print("is_following column already exists (MySQL). Nothing to do.")
EOF
