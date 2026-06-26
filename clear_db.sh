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

from src.common.config import load_config
from src.common.db import get_engine

config = load_config()
engine = get_engine(config)

# Order matters: delete children before parents to respect FK constraints
TABLES = [
    "ai_filtered_views",
    "filters",
    "news_items",
    "series",
    "movies",
    "feed_health",
]

with engine.begin() as conn:
    dialect = engine.dialect.name
    if dialect == "mysql":
        conn.execute(__import__("sqlalchemy").text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in TABLES:
        result = conn.execute(__import__("sqlalchemy").text(f"DELETE FROM `{table}`"))
        print(f"  {table}: {result.rowcount} rows deleted")
    if dialect == "mysql":
        conn.execute(__import__("sqlalchemy").text("SET FOREIGN_KEY_CHECKS = 1"))

print("Done.")
EOF
