#!/usr/bin/env bash
# Idempotent migration: create the saved_entries table (ADR-017 — Saved
# Entries, M16). A brand-new table with no data to backfill from, so unlike
# prior migrations this doesn't ALTER an existing table — it creates
# saved_entries (with its unique index on (source_type, source_id) and its
# secondary index on saved_at) via SQLAlchemy's own table metadata, which is
# inherently idempotent (checkfirst) and correct for both MySQL and SQLite.
#
# Safe to re-run — no-ops if the table already exists.
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

echo "Applying migration 008 (create saved_entries table) to: $DB_URL"

python - <<'EOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
from src.common.models import SavedEntry
from sqlalchemy import create_engine, inspect

cfg = load_config()
engine = create_engine(cfg["database"]["url"])

table = SavedEntry.__table__
already_existed = inspect(engine).has_table(table.name)

table.create(engine, checkfirst=True)

if already_existed:
    print("saved_entries table already exists. Nothing to do.")
else:
    print("Created saved_entries table (with ux_saved_entries_source and ix_saved_entries_saved_at indexes).")
EOF
