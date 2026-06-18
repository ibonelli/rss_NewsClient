#!/usr/bin/env bash
# Pelis-feed pipeline: ingest all feeds, then run filters.
# Intended to be called from cron every ~2 hours.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${REPO_DIR}/.venv/bin/python3"
LOG_DIR="${REPO_DIR}/logs"
LOG_FILE="${LOG_DIR}/pelis_feed_pipeline.log"
MAX_LOG_BYTES=5242880  # 5 MB

mkdir -p "${LOG_DIR}"

# Rotate log if it exceeds MAX_LOG_BYTES
if [ -f "${LOG_FILE}" ] && [ "$(stat -c%s "${LOG_FILE}")" -gt "${MAX_LOG_BYTES}" ]; then
    mv "${LOG_FILE}" "${LOG_FILE}.1"
fi

exec >> "${LOG_FILE}" 2>&1

echo "========================================"
echo "Pipeline start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================"

cd "${REPO_DIR}"

echo "--- Ingester ---"
"${PYTHON}" src/cli/main.py
INGEST_EXIT=$?

if [ ${INGEST_EXIT} -ne 0 ]; then
    echo "Ingester exited with code ${INGEST_EXIT} — skipping filter processor"
    exit ${INGEST_EXIT}
fi

echo "--- Filter processor ---"
"${PYTHON}" src/cli/filter.py
FILTER_EXIT=$?

echo "Pipeline end: $(date -u '+%Y-%m-%d %H:%M:%S UTC') (filter exit: ${FILTER_EXIT})"
exit ${FILTER_EXIT}
