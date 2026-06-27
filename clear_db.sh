#!/usr/bin/env bash
# Clear all data from the pelis-feed database.
# Tables are truncated in dependency order (children before parents).
# Schema and table definitions are preserved — only rows are deleted.
#
# Run from the project root:
#   bash clear_db.sh
#
# Requires: python3 venv at .venv/ with project dependencies installed.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${REPO_DIR}/.venv/bin/python3"

"${PYTHON}" - <<'EOF'
import sys
sys.path.insert(0, ".")

from sqlalchemy import inspect, text
from src.common.config import load_config
from src.common.db import get_engine, init_db

config = load_config()
engine = get_engine(config)

# Order matters: delete children before parents to respect FK constraints
TABLES = [
    "ai_filtered_views",
    "filters",
    "news_items",
    "series_episodes",
    "series",
    "movies",
    "feed_health",
]

existing_tables = set(inspect(engine).get_table_names())

with engine.begin() as conn:
    dialect = engine.dialect.name
    if dialect == "mysql":
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in TABLES:
        if table not in existing_tables:
            print(f"  {table}: (table does not exist — skipped)")
            continue
        result = conn.execute(text(f"DELETE FROM `{table}`"))
        print(f"  {table}: {result.rowcount} rows deleted")
    # Drop old series table if it has the pre-M7 single-table schema
    if "series" in existing_tables:
        series_cols = {c["name"] for c in inspect(engine).get_columns("series")}
        if "season" in series_cols:
            print("  series: old schema detected — dropping table for M7 migration")
            conn.execute(text("DROP TABLE IF EXISTS `series`"))
    if dialect == "mysql":
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

# Recreate tables with current schema (idempotent)
init_db(engine)
print("Schema updated.")
print("Done.")
EOF
