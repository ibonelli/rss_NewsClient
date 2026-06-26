#!/usr/bin/env bash
# Migrate ai_filtered_views table to the M5 schema (ADR-009 / export-import workflow).
#
# Run from the project root:
#   bash migrate_m5_schema.sh
#
# The script is idempotent — it checks the current state before each step
# and skips steps that are already done.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Locate Python (prefer venv)
# ---------------------------------------------------------------------------
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

echo "Using Python: $PYTHON"
echo ""

# ---------------------------------------------------------------------------
# Run migration via Python (reads DB URL from config.yaml)
# ---------------------------------------------------------------------------
"$PYTHON" - <<'PYEOF'
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from src.common.config import load_config
from src.common.db import get_engine
from sqlalchemy import text

config = load_config()
engine = get_engine(config)


def column_exists(conn, table, column):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {"t": table, "c": column})
    return result.scalar() > 0


def index_exists(conn, table, index):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
    ), {"t": table, "i": index})
    return result.scalar() > 0


def fk_exists(conn, table, fk):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
        "AND CONSTRAINT_NAME = :f AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
    ), {"t": table, "f": fk})
    return result.scalar() > 0


TABLE = "ai_filtered_views"

with engine.begin() as conn:

    # ------------------------------------------------------------------
    # Step 1: drop FK + column category_id -> gone
    # ------------------------------------------------------------------
    if column_exists(conn, TABLE, "category_id"):
        if fk_exists(conn, TABLE, "ai_filtered_views_ibfk_2"):
            print("Dropping FK ai_filtered_views_ibfk_2 (category_id -> categories)...")
            conn.execute(text("ALTER TABLE ai_filtered_views DROP FOREIGN KEY ai_filtered_views_ibfk_2"))
        print("Dropping column category_id...")
        conn.execute(text("ALTER TABLE ai_filtered_views DROP COLUMN category_id"))
    else:
        print("column category_id: already removed, skipping.")

    # ------------------------------------------------------------------
    # Step 2: rename news_item_id -> source_item_id
    # ------------------------------------------------------------------
    if column_exists(conn, TABLE, "news_item_id"):
        if fk_exists(conn, TABLE, "ai_filtered_views_ibfk_1"):
            print("Dropping FK ai_filtered_views_ibfk_1 (news_item_id -> news_items)...")
            conn.execute(text("ALTER TABLE ai_filtered_views DROP FOREIGN KEY ai_filtered_views_ibfk_1"))
        print("Renaming column news_item_id -> source_item_id...")
        conn.execute(text(
            "ALTER TABLE ai_filtered_views CHANGE news_item_id source_item_id INT(11) NOT NULL"
        ))
        # Re-add FK under the same name
        if not fk_exists(conn, TABLE, "ai_filtered_views_ibfk_1"):
            print("Re-adding FK ai_filtered_views_ibfk_1 (source_item_id -> news_items)...")
            conn.execute(text(
                "ALTER TABLE ai_filtered_views "
                "ADD CONSTRAINT ai_filtered_views_ibfk_1 "
                "FOREIGN KEY (source_item_id) REFERENCES news_items(id)"
            ))
    else:
        print("column news_item_id: already renamed (source_item_id exists), skipping rename.")
        if not fk_exists(conn, TABLE, "ai_filtered_views_ibfk_1"):
            print("Re-adding FK ai_filtered_views_ibfk_1 (source_item_id -> news_items)...")
            conn.execute(text(
                "ALTER TABLE ai_filtered_views "
                "ADD CONSTRAINT ai_filtered_views_ibfk_1 "
                "FOREIGN KEY (source_item_id) REFERENCES news_items(id)"
            ))

    # ------------------------------------------------------------------
    # Step 3: swap unique index name
    # ------------------------------------------------------------------
    if index_exists(conn, TABLE, "ix_ai_filtered_views_news_item_id"):
        print("Swapping unique index: old name -> ix_ai_filtered_views_source_item_id...")
        # Must drop FK first, swap index, then re-add FK
        if fk_exists(conn, TABLE, "ai_filtered_views_ibfk_1"):
            conn.execute(text("ALTER TABLE ai_filtered_views DROP FOREIGN KEY ai_filtered_views_ibfk_1"))
        conn.execute(text("DROP INDEX ix_ai_filtered_views_news_item_id ON ai_filtered_views"))
        conn.execute(text(
            "CREATE UNIQUE INDEX ix_ai_filtered_views_source_item_id ON ai_filtered_views(source_item_id)"
        ))
        conn.execute(text(
            "ALTER TABLE ai_filtered_views "
            "ADD CONSTRAINT ai_filtered_views_ibfk_1 "
            "FOREIGN KEY (source_item_id) REFERENCES news_items(id)"
        ))
    else:
        print("index ix_ai_filtered_views_news_item_id: already gone, skipping.")

    # ------------------------------------------------------------------
    # Step 4: rename last_filtered_at -> ingested_at
    # ------------------------------------------------------------------
    if column_exists(conn, TABLE, "last_filtered_at"):
        print("Renaming column last_filtered_at -> ingested_at...")
        conn.execute(text(
            "ALTER TABLE ai_filtered_views CHANGE last_filtered_at ingested_at DATETIME NOT NULL"
        ))
    else:
        print("column last_filtered_at: already renamed (ingested_at exists), skipping.")

    # ------------------------------------------------------------------
    # Step 5: add new columns
    # ------------------------------------------------------------------
    new_cols = [
        ("title",        "ADD COLUMN title TEXT NOT NULL DEFAULT '' AFTER feed_name"),
        ("url",          "ADD COLUMN url VARCHAR(2000) NOT NULL DEFAULT '' AFTER title"),
        ("published_at", "ADD COLUMN published_at DATETIME NULL AFTER url"),
        ("category",     "ADD COLUMN category VARCHAR(255) NULL AFTER published_at"),
    ]
    for col_name, ddl in new_cols:
        if not column_exists(conn, TABLE, col_name):
            print(f"Adding column {col_name}...")
            conn.execute(text(f"ALTER TABLE ai_filtered_views {ddl}"))
        else:
            print(f"column {col_name}: already exists, skipping.")

print("")
print("Migration complete. Final schema:")
with engine.connect() as conn:
    result = conn.execute(text("DESCRIBE ai_filtered_views"))
    for row in result:
        print(f"  {row[0]:20s} {row[1]:25s} null={row[2]} key={row[3]}")
PYEOF

echo ""
echo "Done."
