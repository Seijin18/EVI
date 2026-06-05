#!/usr/bin/env bash
# Enable Telegram long polling (no tunnel / domain). SCN-TG-03
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! grep -q '^TELEGRAM_BOT_TOKEN=.\+' .env 2>/dev/null; then
  echo "ERRO: defina TELEGRAM_BOT_TOKEN no .env"
  exit 1
fi

if ! grep -q '^TELEGRAM_MODE=polling' .env 2>/dev/null; then
  echo "Adicione ao .env: TELEGRAM_MODE=polling"
  echo "  echo 'TELEGRAM_MODE=polling' >> .env"
  exit 1
fi

set -a && source .env && set +a

echo "==> Removendo webhook (obrigatório para polling)..."
curl -sf "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true" | head -c 200
echo

echo "==> Recriando agent-api..."
docker compose up -d --build --force-recreate agent-api

echo "==> Aguardando agent healthy..."
sleep 8
docker compose ps agent-api

echo ""
echo "Pronto. Envie uma mensagem ao bot no Telegram."
echo "Logs: docker compose logs -f agent-api | grep -i telegram"
