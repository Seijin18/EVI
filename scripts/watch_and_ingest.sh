#!/bin/bash
# Watches the university folder for new PDFs and triggers agent-api ingest.

set -euo pipefail

ROOT="${EVI_PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
WATCH_DIR="${EVI_WATCH_UNIVERSITY:-$ROOT/watched_folders/university}"
API_URL="${EVI_API_URL:-http://localhost:8002/run-task}"
HOST_PREFIX="${EVI_HOST_WATCH_PREFIX:-$ROOT/watched_folders}"
CONTAINER_PREFIX="${EVI_CONTAINER_WATCH_PREFIX:-/watched_folders}"

echo "Watching $WATCH_DIR for new PDFs (API: $API_URL)..."

if ! command -v inotifywait >/dev/null 2>&1; then
  echo "inotifywait not installed. Install inotify-tools."
  exit 1
fi

inotifywait -m -e close_write -e moved_to --format "%w%f" "$WATCH_DIR" | while read -r FILE
do
    if [[ "$FILE" == *.pdf ]]; then
        echo "New PDF: $FILE"
        DOCKER_PATH="${FILE/#$HOST_PREFIX/$CONTAINER_PREFIX}"
        curl -sS -X POST "$API_URL" \
            -H "Content-Type: application/json" \
            -d "{\"task\": \"ingest_university_pdf\", \"params\": {\"file_path\": \"$DOCKER_PATH\"}}"
        echo -e "\n---"
    fi
done
