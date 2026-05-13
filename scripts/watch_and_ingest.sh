#!/bin/bash
# scripts/watch_and_ingest.sh
# Watches the university folder for new PDF files and triggers the agent API to ingest them.

WATCH_DIR="/home/marshibs/Projects/EVI/watched_folders/university"
API_URL="http://localhost:8000/run-task"

echo "Watching $WATCH_DIR for new PDFs..."

inotifywait -m -e close_write -e moved_to --format "%w%f" "$WATCH_DIR" | while read -r FILE
do
    if [[ "$FILE" == *.pdf ]]; then
        echo "New PDF detected: $FILE"
        echo "Triggering ingestion..."
        
        # We need the path mapping considering agent runs in docker, mapped from ~/Projects/EVI
        # Host: /home/marshibs/Projects/EVI/watched_folders/university/note.pdf
        # Docker: /app/watched_folders/university/note.pdf
        
        # Replace the host path with the container path
        DOCKER_PATH="${FILE/\/home\/marshibs\/Projects\/EVI\/watched_folders/\/watched_folders}"
        
        curl -X POST "$API_URL" \
            -H "Content-Type: application/json" \
            -d "{\"task\": \"ingest_university_pdf\", \"params\": {\"file_path\": \"$DOCKER_PATH\"}}"
        
        echo -e "\n---"
    fi
done