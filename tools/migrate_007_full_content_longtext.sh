#!/usr/bin/env bash
# Idempotent migration: widen news_items.full_content from TEXT to LONGTEXT
# on MySQL. MySQL's TEXT type caps at 65,535 bytes; some news feeds provide
# the full article body as raw HTML via a <content> extension, which can
# exceed that and fail ingestion with "Data too long for column
# 'full_content'" (1406). SQLite's TEXT has no such limit — no-op there.
#
# Safe to re-run — skips the ALTER if the column is already LONGTEXT.
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

echo "Applying migration 007 (news_items.full_content -> LONGTEXT) to: $DB_URL"

python - <<'EOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
from sqlalchemy import create_engine, text

cfg = load_config()
db_url = cfg["database"]["url"]
engine = create_engine(db_url)

if db_url.startswith("sqlite"):
    print("SQLite has no TEXT length limit. Nothing to do.")
    sys.exit(0)

with engine.connect() as conn:
    table_count = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'news_items'"
    )).scalar()
    if table_count == 0:
        print("news_items table does not exist yet (will be created correctly by init_db()). Skipping.")
        sys.exit(0)

    data_type = conn.execute(text(
        "SELECT DATA_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'news_items' AND COLUMN_NAME = 'full_content'"
    )).scalar()

    if data_type == "longtext":
        print("news_items.full_content is already LONGTEXT. Nothing to do.")
    else:
        conn.execute(text("ALTER TABLE news_items MODIFY full_content LONGTEXT NOT NULL"))
        conn.commit()
        print(f"news_items.full_content widened from {data_type} to LONGTEXT.")
EOF
