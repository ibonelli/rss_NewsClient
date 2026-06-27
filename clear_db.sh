#!/usr/bin/env bash
# Clear all data from the pelis-feed database.
# Uses DELETE (not TRUNCATE) in FK-safe order so no FK disable is needed.
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

# Children before parents — DELETE in this order works with FK constraints intact.
# (TRUNCATE would need FK_CHECKS=0; DELETE does not, as long as order is correct.)
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

# Detect pre-M7 single-table series schema and drop it so init_db can recreate correctly
if "series" in existing_tables:
    series_cols = {c["name"] for c in inspect(engine).get_columns("series")}
    if "season" in series_cols:
        print("  series: old schema detected — dropping for M7 migration")
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            conn.execute(text("DROP TABLE IF EXISTS `series`"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        existing_tables.discard("series")
        existing_tables.discard("series_episodes")

for table in TABLES:
    if table not in existing_tables:
        print(f"  {table}: (does not exist — skipped)")
        continue
    with engine.begin() as conn:
        result = conn.execute(text(f"DELETE FROM `{table}`"))
    print(f"  {table}: {result.rowcount} rows deleted")

# Recreate any missing tables with current schema (idempotent)
init_db(engine)
print("Schema up to date.")
print("Done.")
EOF
