#!/usr/bin/env bash
# Pelis-feed pipeline: ingest all feeds, then run filters.
# Intended to be called from cron every ~2 hours.
#
# All output goes to logs/pelis_feed_pipeline.log. The script prints nothing
# to its own stdout unless the run had an error (non-zero exit, or an ERROR /
# CRITICAL / Traceback line in this run's log section) — in that case it
# prints a report, which cron mails to MAILTO. Don't redirect this script's
# output in the crontab line, or the error report is lost.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${REPO_DIR}/venv/bin/python"
LOG_DIR="${REPO_DIR}/logs"
LOG_FILE="${LOG_DIR}/pelis_feed_pipeline.log"
MAX_LOG_BYTES=5242880  # 5 MB
ERROR_PATTERN=' (ERROR|CRITICAL) |^Traceback'

mkdir -p "${LOG_DIR}"

# Rotate log if it exceeds MAX_LOG_BYTES
if [ -f "${LOG_FILE}" ] && [ "$(stat -c%s "${LOG_FILE}")" -gt "${MAX_LOG_BYTES}" ]; then
    mv "${LOG_FILE}" "${LOG_FILE}.1"
fi

# Byte offset where this run's log section starts.
RUN_OFFSET=0
[ -f "${LOG_FILE}" ] && RUN_OFFSET="$(stat -c%s "${LOG_FILE}")"

INGEST_EXIT="not run"
FILTER_EXIT="not run"

# Keep the original stdout (what cron mails) on fd 3, then send everything to the log.
exec 3>&1
exec >> "${LOG_FILE}" 2>&1

report_on_error() {
    local script_exit=$?
    local run_log error_lines error_count
    run_log="$(tail -c +$((RUN_OFFSET + 1)) "${LOG_FILE}")"
    error_lines="$(grep -E "${ERROR_PATTERN}" <<< "${run_log}" || true)"
    error_count=0
    [ -n "${error_lines}" ] && error_count="$(wc -l <<< "${error_lines}")"

    if [ "${script_exit}" -eq 0 ] && [ "${error_count}" -eq 0 ]; then
        return
    fi

    {
        echo "pelis-feed pipeline reported errors on $(hostname)"
        echo "Script exit: ${script_exit} | ingester exit: ${INGEST_EXIT} | filter exit: ${FILTER_EXIT} | error lines: ${error_count}"
        echo
        if [ -n "${error_lines}" ]; then
            echo "=== Error lines ==="
            echo "${error_lines}"
            echo
        fi
        echo "=== This run's log ==="
        echo "${run_log}"
        echo
        echo "Full log: ${LOG_FILE}"
    } >&3
}
trap report_on_error EXIT

echo "========================================"
echo "Pipeline start: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================"

cd "${REPO_DIR}"

echo "--- Ingester ---"
INGEST_EXIT=0
"${PYTHON}" src/cli/main.py || INGEST_EXIT=$?

if [ "${INGEST_EXIT}" -ne 0 ]; then
    echo "Ingester exited with code ${INGEST_EXIT} — skipping filter processor"
    exit "${INGEST_EXIT}"
fi

echo "--- Filter processor ---"
FILTER_EXIT=0
"${PYTHON}" src/cli/filter.py || FILTER_EXIT=$?

echo "Pipeline end: $(date -u '+%Y-%m-%d %H:%M:%S UTC') (filter exit: ${FILTER_EXIT})"
exit "${FILTER_EXIT}"
