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
docker compose up -d --force-recreate --wait agent-api
chmod +x "${ROOT}/scripts/evi-wait-agent-api.sh"
"${ROOT}/scripts/evi-wait-agent-api.sh"

echo "==> 1/3 sendMessage..."
docker compose exec -T agent-api python -c "
from services.telegram_notify import send_telegram_message
assert send_telegram_message('EVI: teste 1/3 — sendMessage'), 'sendMessage failed'
print('OK sendMessage')
"

echo "==> 2/3 webhook + reply..."
docker compose exec -T \
  -e EVI_FIXTURES_DIR=/fixtures \
  -e EVI_API_URL=http://127.0.0.1:8000 \
  agent-api python3 /app/testing/cli.py telegram --live-telegram --strict

echo "==> 3/3 digest compromisso urgente..."
docker compose exec -T agent-api python -c "
from datetime import datetime
from db import init_db, insert_pending_commitment
from services.commitment_notify import maybe_notify_new_pending
init_db()
sid = f'tg-digest-verify-{datetime.utcnow().strftime(\"%Y%m%d%H%M%S\")}'
rid = insert_pending_commitment(
    source='evi-test', source_id=sid,
    ctype='event', title='Teste digest Telegram',
    event_date='2026-12-10', priority='urgent', raw_text='SCN-WA-12',
)
assert rid, f'insert failed source_id={sid}'
assert maybe_notify_new_pending([rid], ['urgent']), 'digest not sent'
print('OK digest rid=', rid)
"

echo ""
echo "Telegram E2E: 3/3 OK — confira as mensagens no app Telegram."
