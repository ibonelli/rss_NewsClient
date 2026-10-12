#!/usr/bin/env bash
# Back up the application database configured in config.yaml (database.url).
#
# Run from anywhere:
#   tools/backup_db.sh [OUTPUT_DIR]
#
# OUTPUT_DIR defaults to ./backups (project root). Writes a timestamped,
# gzip-compressed file:
#   MySQL  -> pelis_feed-YYYYMMDD-HHMMSS.sql.gz  (mysqldump, --single-transaction)
#   SQLite -> pelis_feed-YYYYMMDD-HHMMSS.db.gz   (sqlite3 .backup, safe while the web UI runs)
#
# Optional env vars:
#   BACKUP_KEEP_DAYS  delete backups in OUTPUT_DIR older than N days (default: keep all)
#
# The DB URL is parsed with SQLAlchemy's make_url (same load_config() fallback
# to config.yaml.example as the app). The MySQL password is passed through a
# temporary mode-600 defaults file, never on the command line.
#
# Restore:
#   MySQL:  gunzip -c FILE.sql.gz | mysql -u USER -p DBNAME
#   SQLite: stop the web UI, then gunzip -c FILE.db.gz > pelis_feed.db
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

OUT_DIR="${1:-$PROJECT_ROOT/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-}"

if [ -f ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
elif [ -f "venv/bin/python3" ]; then
    PYTHON="venv/bin/python3"
else
    PYTHON="$(command -v python3 || command -v python)"
fi

# Emit shell-quoted assignments for the parsed URL components.
DB_VARS="$("$PYTHON" - <<'PYEOF'
import shlex, sys
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from sqlalchemy.engine import make_url
from src.common.config import load_config

url = make_url(load_config()["database"]["url"])
fields = {
    "DB_BACKEND": url.get_backend_name(),
    "DB_HOST": url.host or "",
    "DB_PORT": str(url.port or ""),
    "DB_USER": url.username or "",
    # Escaped for a double-quoted MySQL option-file value.
    "DB_PASS": (url.password or "").replace("\\", "\\\\").replace('"', '\\"'),
    "DB_NAME": url.database or "",
}
for k, v in fields.items():
    print(f"{k}={shlex.quote(v)}")
PYEOF
)"
eval "$DB_VARS"

if [ -z "$DB_NAME" ]; then
    echo "ERROR: no database name/path in database.url" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
BASE="$(basename "$DB_NAME")"
BASE="${BASE%.db}"

case "$DB_BACKEND" in
    mysql)
        command -v mysqldump >/dev/null || { echo "ERROR: mysqldump not found" >&2; exit 1; }
        OUT_FILE="$OUT_DIR/${BASE}-${STAMP}.sql.gz"
        DEFAULTS_FILE="$(mktemp)"
        chmod 600 "$DEFAULTS_FILE"
        trap 'rm -f "$DEFAULTS_FILE"' EXIT
        {
            echo "[client]"
            [ -n "$DB_USER" ] && echo "user=$DB_USER"
            [ -n "$DB_PASS" ] && echo "password=\"$DB_PASS\""
            [ -n "$DB_HOST" ] && echo "host=$DB_HOST"
            [ -n "$DB_PORT" ] && echo "port=$DB_PORT"
        } > "$DEFAULTS_FILE"

        echo "Dumping MySQL database '$DB_NAME' to $OUT_FILE"
        # pipefail ensures a mysqldump failure fails the script, not just gzip's status.
        if ! mysqldump --defaults-extra-file="$DEFAULTS_FILE" \
                --single-transaction --routines --triggers --no-tablespaces \
                --default-character-set=utf8mb4 \
                "$DB_NAME" | gzip > "$OUT_FILE"; then
            rm -f "$OUT_FILE"
            echo "ERROR: mysqldump failed" >&2
            exit 1
        fi
        ;;
    sqlite)
        command -v sqlite3 >/dev/null || { echo "ERROR: sqlite3 not found" >&2; exit 1; }
        if [ ! -f "$DB_NAME" ]; then
            echo "ERROR: SQLite file not found: $DB_NAME" >&2
            exit 1
        fi
        OUT_FILE="$OUT_DIR/${BASE}-${STAMP}.db.gz"
        TMP_DB="$(mktemp)"
        trap 'rm -f "$TMP_DB"' EXIT
        echo "Backing up SQLite database '$DB_NAME' to $OUT_FILE"
        sqlite3 "$DB_NAME" ".backup '$TMP_DB'"
        gzip -c "$TMP_DB" > "$OUT_FILE"
        ;;
    *)
        echo "ERROR: unsupported database backend '$DB_BACKEND'" >&2
        exit 1
        ;;
esac

echo "Backup written: $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"

if [ -n "$KEEP_DAYS" ]; then
    echo "Pruning backups older than $KEEP_DAYS days in $OUT_DIR"
    find "$OUT_DIR" -maxdepth 1 -type f \( -name "${BASE}-*.sql.gz" -o -name "${BASE}-*.db.gz" \) \
        -mtime +"$KEEP_DAYS" -print -delete
fi
