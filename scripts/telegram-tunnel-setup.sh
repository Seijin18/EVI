#!/usr/bin/env bash
# Telegram remote chat: test Windmill route + Cloudflare tunnel + setWebhook
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a && source .env && set +a

: "${TELEGRAM_BOT_TOKEN:?Defina TELEGRAM_BOT_TOKEN no .env}"
: "${WINDMILL_TELEGRAM_WEBHOOK_TOKEN:?Defina WINDMILL_TELEGRAM_WEBHOOK_TOKEN no .env}"

WM_BASE="${WINDMILL_TELEGRAM_PUBLIC_BASE:-http://localhost:8001}"
WM_PATH="${WINDMILL_TELEGRAM_ROUTE_PATH:-/api/r/f/integrations/telegram_to_evi}"
# Route /api/r/... = HTTP trigger criado na aba Triggers do script
WM_URL="${WM_BASE}${WM_PATH}?token=${WINDMILL_TELEGRAM_WEBHOOK_TOKEN}"

echo "==> 1/4 Teste local Windmill (body Telegram cru)..."
HTTP=$(curl -s -o /tmp/evi_tg_wm.json -w '%{http_code}' -X POST "$WM_URL" \
  -H 'Content-Type: application/json' \
  -d "{\"update_id\":$(date +%s),\"message\":{\"message_id\":1,\"chat\":{\"id\":${TELEGRAM_CHAT_ID:-933619568},\"type\":\"private\"},\"text\":\"ping tunnel setup\"}}")
echo "Windmill HTTP $HTTP"
head -c 500 /tmp/evi_tg_wm.json; echo

if [[ "$HTTP" != "200" && "$HTTP" != "201" ]]; then
  echo "Falhou. Rode: ./scripts/wmill-sync.sh (script telegram_to_evi atualizado)"
  exit 1
fi

CF="${CLOUDFLARED:-}"
if [[ -z "$CF" ]]; then
  CF="$(command -v cloudflared || true)"
fi
if [[ -z "$CF" && -x "$HOME/.local/bin/cloudflared" ]]; then
  CF="$HOME/.local/bin/cloudflared"
fi
if [[ -z "$CF" ]]; then
  echo "==> Instalando cloudflared em ~/.local/bin ..."
  mkdir -p "$HOME/.local/bin"
  curl -fsSL -o "$HOME/.local/bin/cloudflared" \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$HOME/.local/bin/cloudflared"
  CF="$HOME/.local/bin/cloudflared"
fi

echo "==> 2/4 Iniciando tunnel (porta 8001)..."
pkill -f 'cloudflared tunnel --url http://localhost:8001' 2>/dev/null || true
"$CF" tunnel --url http://localhost:8001 > /tmp/evi_cloudflared.log 2>&1 &
sleep 5
PUBLIC=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' /tmp/evi_cloudflared.log | head -1)
if [[ -z "$PUBLIC" ]]; then
  echo "Tunnel URL não encontrada. Log:"
  tail -20 /tmp/evi_cloudflared.log
  exit 1
fi
echo "Tunnel público: $PUBLIC"

WEBHOOK_URL="${PUBLIC}${WM_PATH}?token=${WINDMILL_TELEGRAM_WEBHOOK_TOKEN}"
echo "==> 3/4 setWebhook..."
curl -s -G "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=${WEBHOOK_URL}" | tee /tmp/evi_setwebhook.json
echo

echo "==> 4/4 getWebhookInfo..."
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | head -c 600
echo
echo ""
echo "Pronto. Envie uma mensagem ao bot no Telegram."
echo "Tunnel log: /tmp/evi_cloudflared.log"
