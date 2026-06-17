#!/usr/bin/env bash
# Wait until agent-api responds (host :8002 or in-container :8000).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

URL="${EVI_WAIT_URL:-http://localhost:8002/}"
MAX="${EVI_WAIT_MAX_SEC:-90}"
INTERVAL="${EVI_WAIT_INTERVAL_SEC:-2}"

echo "==> Aguardando agent-api em ${URL} (até ${MAX}s)..."
deadline=$((SECONDS + MAX))
while (( SECONDS < deadline )); do
  if curl -sf --max-time 3 "${URL}" >/dev/null 2>&1; then
    echo "OK agent-api respondeu"
    exit 0
  fi
  if docker compose ps agent-api 2>/dev/null | grep -q "(healthy)"; then
    sleep 1
    if curl -sf --max-time 3 "${URL}" >/dev/null 2>&1; then
      echo "OK agent-api healthy"
      exit 0
    fi
  fi
  sleep "${INTERVAL}"
done

echo "ERRO: agent-api não respondeu em ${MAX}s (${URL})" >&2
docker compose ps agent-api 2>/dev/null || true
docker compose logs agent-api --tail 30 2>/dev/null || true
exit 1
