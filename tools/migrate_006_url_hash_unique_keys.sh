#!/usr/bin/env bash
# Idempotent migration: replace UNIQUE constraints on long URL columns with
# UNIQUE constraints on a fixed-length SHA-256 hash column instead.
#
# Root cause: under utf8mb4 (4 bytes/char), movies.torrent_url (VARCHAR(1000))
# UNIQUE is a 4000-byte index key, and news_items/design_items UNIQUE
# (url VARCHAR(2000), feed_name) is up to 9020 bytes — both over InnoDB's
# 3072-byte single-key-part limit, so CREATE TABLE fails outright on MySQL.
#
# For each of movies.torrent_url, news_items.url, design_items.url: adds a
# CHAR(64) *_hash column (SHA-256 hex digest via MySQL's SHA2() / Python
# hashlib for SQLite), backfills it, makes it (or (*_hash, feed_name)) the
# UNIQUE key, and drops the old oversized unique index on MySQL. SQLite has
# no index-key-length limit, so on SQLite the old inline unique constraint is
# left in place (harmless) rather than rebuilding the table to remove it.
#
# Safe to re-run — skips any step already applied. No-ops entirely for a
# table that doesn't exist yet (init_db()/create_all() will create it with
# the corrected schema directly).
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

echo "Applying migration 006 (url hash unique keys: movies, news_items, design_items) to: $DB_URL"

python - <<'EOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from src.common.config import load_config
from src.common.models import hash_url
from sqlalchemy import create_engine, text

cfg = load_config()
db_url = cfg["database"]["url"]
engine = create_engine(db_url)
is_sqlite = db_url.startswith("sqlite")

# (table, raw URL column, new hash column, new unique index name, extra columns in the unique key)
TABLES = [
    ("movies", "torrent_url", "torrent_url_hash", "ux_movies_torrent_url_hash", []),
    ("news_items", "url", "url_hash", "ix_news_items_url_hash_feed", ["feed_name"]),
    ("design_items", "url", "url_hash", "ix_design_items_url_hash_feed", ["feed_name"]),
]


def table_exists(conn, table):
    if is_sqlite:
        return conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name = :t"), {"t": table}
        ).first() is not None
    return conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": table}).scalar() > 0


def get_columns(conn, table):
    if is_sqlite:
        return [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
    return [row[0] for row in conn.execute(text(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
    ), {"t": table}).fetchall()]


def mysql_index_exists(conn, table, index_name):
    return conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i"
    ), {"t": table, "i": index_name}).scalar() > 0


def mysql_old_unique_indexes(conn, table, column):
    """Names of unique indexes whose first key part is `column` (the old raw-URL unique key)."""
    rows = conn.execute(text(
        "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t "
        "AND COLUMN_NAME = :c AND SEQ_IN_INDEX = 1 AND NON_UNIQUE = 0"
    ), {"t": table, "c": column}).fetchall()
    return [r[0] for r in rows]


with engine.connect() as conn:
    for table, url_col, hash_col, new_index, extra_cols in TABLES:
        if not table_exists(conn, table):
            print(f"{table}: table does not exist yet (will be created correctly by init_db()). Skipping.")
            continue

        cols = get_columns(conn, table)

        if hash_col not in cols:
            stmt = (
                f"ALTER TABLE {table} ADD COLUMN {hash_col} CHAR(64)"
                if is_sqlite else
                f"ALTER TABLE {table} ADD COLUMN {hash_col} CHAR(64) NULL"
            )
            conn.execute(text(stmt))
            conn.commit()
            print(f"{table}: added {hash_col} column.")
        else:
            print(f"{table}: {hash_col} column already exists.")

        if is_sqlite:
            rows = conn.execute(text(f"SELECT id, {url_col} FROM {table} WHERE {hash_col} IS NULL")).fetchall()
            for row_id, url in rows:
                conn.execute(
                    text(f"UPDATE {table} SET {hash_col} = :h WHERE id = :id"),
                    {"h": hash_url(url or ""), "id": row_id},
                )
            conn.commit()
            print(f"{table}: backfilled {len(rows)} row(s) (SQLite).")
        else:
            result = conn.execute(text(
                f"UPDATE {table} SET {hash_col} = SHA2({url_col}, 256) WHERE {hash_col} IS NULL"
            ))
            conn.commit()
            print(f"{table}: backfilled {result.rowcount} row(s) (MySQL).")

        if is_sqlite:
            # No index-key-length limit on SQLite — leave the column nullable
            # and any pre-existing unique constraint on the raw URL column in
            # place rather than rebuilding the table to remove it.
            continue

        conn.execute(text(f"ALTER TABLE {table} MODIFY {hash_col} CHAR(64) NOT NULL"))
        conn.commit()

        if not mysql_index_exists(conn, table, new_index):
            key_cols = ", ".join([hash_col] + extra_cols)
            conn.execute(text(f"ALTER TABLE {table} ADD UNIQUE INDEX {new_index} ({key_cols})"))
            conn.commit()
            print(f"{table}: added unique index {new_index} ({key_cols}).")
        else:
            print(f"{table}: unique index {new_index} already exists.")

        for old_index in mysql_old_unique_indexes(conn, table, url_col):
            conn.execute(text(f"ALTER TABLE {table} DROP INDEX {old_index}"))
            conn.commit()
            print(f"{table}: dropped old unique index {old_index} on {url_col}.")
EOF
