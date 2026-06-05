#!/usr/bin/env bash
# Stable Telegram webhook via Cloudflare named tunnel (free plan).
# Prereqs: domain on Cloudflare, `cloudflared tunnel login`, tunnel created + DNS route.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a && source .env && set +a

: "${TELEGRAM_BOT_TOKEN:?Defina TELEGRAM_BOT_TOKEN no .env}"
: "${WINDMILL_TELEGRAM_WEBHOOK_TOKEN:?Defina WINDMILL_TELEGRAM_WEBHOOK_TOKEN no .env}"
: "${CLOUDFLARE_TUNNEL_NAME:?Defina CLOUDFLARE_TUNNEL_NAME (ex: evi-windmill)}"
: "${CLOUDFLARE_TUNNEL_HOSTNAME:?Defina CLOUDFLARE_TUNNEL_HOSTNAME (ex: wm.seudominio.com)}"

WM_PATH="${WINDMILL_TELEGRAM_ROUTE_PATH:-/api/r/f/integrations/telegram_to_evi}"
PUBLIC_BASE="https://${CLOUDFLARE_TUNNEL_HOSTNAME}"
WEBHOOK_URL="${PUBLIC_BASE}${WM_PATH}?token=${WINDMILL_TELEGRAM_WEBHOOK_TOKEN}"

CF="${CLOUDFLARED:-}"
if [[ -z "$CF" ]]; then
  CF="$(command -v cloudflared || true)"
fi
if [[ -z "$CF" && -x "$HOME/.local/bin/cloudflared" ]]; then
  CF="$HOME/.local/bin/cloudflared"
fi
if [[ -z "$CF" ]]; then
  echo "Instale cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
  exit 1
fi

CONFIG="${CLOUDFLARE_TUNNEL_CONFIG:-$HOME/.cloudflared/config.yml}"
if [[ ! -f "$CONFIG" ]]; then
  echo "Crie $CONFIG com ingress para localhost:8001. Exemplo:"
  cat <<EOF

tunnel: <TUNNEL_UUID>
credentials-file: $HOME/.cloudflared/<TUNNEL_UUID>.json
ingress:
  - hostname: ${CLOUDFLARE_TUNNEL_HOSTNAME}
    service: http://localhost:8001
  - service: http_status:404

Comandos iniciais (uma vez):
  cloudflared tunnel login
  cloudflared tunnel create ${CLOUDFLARE_TUNNEL_NAME}
  cloudflared tunnel route dns ${CLOUDFLARE_TUNNEL_NAME} ${CLOUDFLARE_TUNNEL_HOSTNAME}
EOF
  exit 1
fi

echo "==> 1/4 Teste local Windmill..."
LOCAL_URL="http://localhost:8001${WM_PATH}?token=${WINDMILL_TELEGRAM_WEBHOOK_TOKEN}"
HTTP=$(curl -s -o /tmp/evi_tg_wm.json -w '%{http_code}' -X POST "$LOCAL_URL" \
  -H 'Content-Type: application/json' \
  -d "{\"update_id\":$(date +%s),\"message\":{\"message_id\":1,\"chat\":{\"id\":${TELEGRAM_CHAT_ID:-0},\"type\":\"private\"},\"text\":\"ping named tunnel\"}}")
echo "Windmill local HTTP $HTTP"
if [[ "$HTTP" != "200" && "$HTTP" != "201" ]]; then
  head -c 400 /tmp/evi_tg_wm.json; echo
  exit 1
fi

echo "==> 2/4 Iniciando named tunnel (${CLOUDFLARE_TUNNEL_NAME})..."
pkill -f "cloudflared tunnel run ${CLOUDFLARE_TUNNEL_NAME}" 2>/dev/null || true
"$CF" tunnel --config "$CONFIG" run "${CLOUDFLARE_TUNNEL_NAME}" > /tmp/evi_cloudflared_named.log 2>&1 &
sleep 5

echo "==> 3/4 Verificando rota pública..."
if ! curl -sf -o /dev/null -m 10 "${PUBLIC_BASE}/" 2>/dev/null; then
  echo "Aviso: ${PUBLIC_BASE} ainda não responde (tunnel pode levar ~30s). Log:"
  tail -15 /tmp/evi_cloudflared_named.log
fi

echo "==> 4/4 setWebhook estável..."
curl -s -G "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=${WEBHOOK_URL}" | tee /tmp/evi_setwebhook_named.json
echo
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" | head -c 600
echo
echo ""
echo "Webhook estável: ${WEBHOOK_URL}"
echo "Tunnel log: /tmp/evi_cloudflared_named.log"
echo "Fallback dev (URL efêmera): ./scripts/telegram-tunnel-setup.sh"
