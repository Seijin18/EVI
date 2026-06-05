#!/usr/bin/env bash
# Telegram E2E: sendMessage, webhook reply, digest (SCN-TG-02, SCN-WA-12)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! grep -q '^TELEGRAM_BOT_TOKEN=.\+' .env 2>/dev/null; then
  echo "ERRO: salve TELEGRAM_BOT_TOKEN no .env (Ctrl+S) e rode:"
  echo "  docker compose up -d --force-recreate agent-api"
  exit 1
fi

echo "==> Recriando agent-api com .env atual..."
docker compose up -d --force-recreate agent-api

echo "==> 1/3 sendMessage..."
docker compose exec -T agent-api python -c "
from services.telegram_notify import send_telegram_message
assert send_telegram_message('EVI: teste 1/3 — sendMessage'), 'sendMessage failed'
print('OK sendMessage')
"

echo "==> 2/3 webhook + reply (Ollama ~15–45s com qwen2.5:3b)..."
export PYTHONPATH="${ROOT}/agent"
set -a && source .env && set +a
export EVI_API_URL="${EVI_API_URL:-http://localhost:8002}"
./scripts/evi-test telegram --live-telegram

echo "==> 3/3 digest compromisso urgente..."
docker compose exec -T agent-api python -c "
from db import init_db, insert_pending_commitment
from services.commitment_notify import maybe_notify_new_pending
init_db()
rid = insert_pending_commitment(
    source='evi-test', source_id='tg-digest-verify',
    ctype='event', title='Teste digest Telegram',
    event_date='2026-06-10', priority='urgent', raw_text='SCN-WA-12',
)
assert rid, 'insert failed'
assert maybe_notify_new_pending([rid], ['urgent']), 'digest not sent'
print('OK digest rid=', rid)
"

echo ""
echo "Telegram E2E: 3/3 OK — confira as mensagens no app Telegram."
