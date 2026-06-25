#!/usr/bin/env bash
# Idempotent migration: add is_ignored column to the series table.
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
print(cfg.database.url)
EOF
)
fi

echo "Applying migration 002 (series.is_ignored) to: $DB_URL"

python - <<EOF
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
from sqlalchemy import create_engine, text

cfg = load_config()
engine = create_engine(cfg.database.url)

with engine.connect() as conn:
    if cfg.database.url.startswith("sqlite"):
        result = conn.execute(text("PRAGMA table_info(series)")).fetchall()
        col_names = [row[1] for row in result]
        if "is_ignored" not in col_names:
            conn.execute(text("ALTER TABLE series ADD COLUMN is_ignored BOOLEAN NOT NULL DEFAULT 0"))
            conn.commit()
            print("Added is_ignored column (SQLite).")
        else:
            print("is_ignored column already exists (SQLite). Nothing to do.")
    else:
        # MySQL: check information_schema
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'series' AND COLUMN_NAME = 'is_ignored'"
        )).scalar()
        if result == 0:
            conn.execute(text("ALTER TABLE series ADD COLUMN is_ignored BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.commit()
            print("Added is_ignored column (MySQL).")
        else:
            print("is_ignored column already exists (MySQL). Nothing to do.")
EOF
