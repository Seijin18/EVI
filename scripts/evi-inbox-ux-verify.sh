#!/usr/bin/env bash
# Inbox UX E2E: mock harness + optional live Windmill + chat (SCN-UX-INBOX-*)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Recriando agent-api com .env atual..."
docker compose up -d --build --wait agent-api
chmod +x "${ROOT}/scripts/evi-wait-agent-api.sh"
"${ROOT}/scripts/evi-wait-agent-api.sh"

echo "==> 1/4 offline inbox-ux (mock)..."
./scripts/evi-test inbox-ux

echo "==> 2/4 runtime-v3..."
./scripts/evi-test runtime-v3

echo "==> 3/4 email live Windmill (Gmail OAuth)..."
if ./scripts/evi-test email --live-windmill; then
  echo "OK email live"
else
  echo "WARN: email live skipped or failed (OAuth/token)"
fi

echo "==> 4/4 chat API (Gemini — pode levar ~30–120s)..."
./scripts/evi-test chat --strict

echo ""
echo "Inbox UX E2E harness concluído."
echo "Live manual: Telegram «Revise meus emails» → summarize_inbox; «Apaga AliExpress e OLX» → delete_emails_by_query"
