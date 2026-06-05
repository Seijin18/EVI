#!/usr/bin/env bash
# Create/configure Evolution API instance "evi" and webhook → agent-api.
# Usage: ./scripts/setup-evolution.sh [--reset]  # --reset deletes instance and recreates (fresh QR)
set -euo pipefail

RESET=false
if [ "${1:-}" = "--reset" ]; then
  RESET=true
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

BASE="${EVOLUTION_SERVER_URL:-http://localhost:8082}"
KEY="${EVOLUTION_API_KEY:-evi-dev-key}"
INSTANCE="${EVOLUTION_INSTANCE_NAME:-evi}"
WEBHOOK_URL="${EVOLUTION_WEBHOOK_URL:-http://agent-api:8000/webhooks/evolution}"
EVI_KEY="${EVI_API_KEY:-}"
# Whitelist needs group webhooks from Evolution (agent filter drops non-listed groups).
GROUPS_IGNORE=true
GROUPS_IGNORE_PY=True
if [ -n "${EVI_WHATSAPP_GROUP_WHITELIST:-}" ]; then
  GROUPS_IGNORE=false
  GROUPS_IGNORE_PY=False
fi

api() {
  curl -sS -H "apikey: ${KEY}" -H "Content-Type: application/json" "$@"
}

echo "==> Evolution API: ${BASE}"
if ! api "${BASE}/" | grep -q '"status":200'; then
  echo "Evolution not reachable. Run: docker compose up -d evolution-api redis postgres agent-api"
  exit 1
fi

if [ "$RESET" = true ]; then
  echo "==> Removing instance '${INSTANCE}' (logout + delete)"
  api -X DELETE "${BASE}/instance/logout/${INSTANCE}" >/dev/null 2>&1 || true
  api -X DELETE "${BASE}/instance/delete/${INSTANCE}" >/dev/null 2>&1 || true
  sleep 2
fi

exists=$(api "${BASE}/instance/fetchInstances" | python3 -c "
import json,sys
data=json.load(sys.stdin)
names=[i.get('instance',{}).get('instanceName') or i.get('name') or i.get('instanceName') for i in (data if isinstance(data,list) else [])]
print('yes' if '${INSTANCE}' in names else 'no')
" 2>/dev/null || echo "no")

if [ "$exists" = "yes" ]; then
  echo "==> Instance '${INSTANCE}' already exists — updating webhook"
else
  echo "==> Creating instance '${INSTANCE}'"
  headers_json="{}"
  if [ -n "$EVI_KEY" ]; then
    headers_json=$(python3 -c "import json; print(json.dumps({'X-Api-Key': '''${EVI_KEY}'''}))")
  fi
  payload=$(python3 <<PY
import json
webhook = {
  "enabled": True,
  "url": "${WEBHOOK_URL}",
  "webhookByEvents": False,
  "webhookBase64": False,
  "events": ["MESSAGES_UPSERT"],
}
headers = json.loads('''${headers_json}''')
if headers:
    webhook["headers"] = headers
print(json.dumps({
  "instanceName": "${INSTANCE}",
  "qrcode": True,
  "integration": "WHATSAPP-BAILEYS",
  "syncFullHistory": False,
  "groupsIgnore": ${GROUPS_IGNORE_PY},
  "readMessages": False,
  "webhook": webhook,
}))
PY
)
  api -X POST "${BASE}/instance/create" -d "$payload" | python3 -m json.tool
fi

echo "==> Setting webhook on instance"
wh_payload=$(python3 <<PY
import json
webhook = {
  "enabled": True,
  "url": "${WEBHOOK_URL}",
  "webhookByEvents": False,
  "webhookBase64": False,
  "events": ["MESSAGES_UPSERT"],
}
print(json.dumps({"webhook": webhook}))
PY
)
api -X POST "${BASE}/webhook/set/${INSTANCE}" -d "$wh_payload" | python3 -m json.tool || true

echo "==> Instance settings (no full history sync, groupsIgnore=${GROUPS_IGNORE})"
api -X POST "${BASE}/settings/set/${INSTANCE}" -d "{
  \"syncFullHistory\": false,
  \"groupsIgnore\": ${GROUPS_IGNORE},
  \"readMessages\": false,
  \"readStatus\": false,
  \"rejectCall\": false,
  \"alwaysOnline\": false
}" | python3 -m json.tool || true

echo ""
echo "==> Connection / QR code"
connect_json=$(api "${BASE}/instance/connect/${INSTANCE}")
echo "$connect_json" | python3 -c "
import json,sys
d=json.load(sys.stdin)
qr=d.get('qrcode') if isinstance(d.get('qrcode'),dict) else {}
base=d.get('base64') or qr.get('base64')
count=qr.get('count', d.get('count'))
if base and len(str(base))>80:
    print('QR gerado (count=%s). Abra o Manager ou logs/evolution_qr.png' % count)
    print('  ${BASE}/manager')
elif d.get('pairingCode'):
    print('Pairing code:', d.get('pairingCode'))
else:
    print(json.dumps(d, indent=2)[:800])
    print('Se count=0, use imagem evoapicloud/evolution-api:v2.3.7 e ./scripts/setup-evolution.sh --reset')
"
echo "$connect_json" | python3 -c "
import json,sys,base64,pathlib
d=json.load(sys.stdin)
qr=d.get('qrcode') if isinstance(d.get('qrcode'),dict) else {}
b=d.get('base64') or qr.get('base64')
if b and len(str(b))>80:
    p=pathlib.Path('${ROOT}/logs/evolution_qr.png')
    p.parent.mkdir(parents=True, exist_ok=True)
    raw=base64.b64decode(b.split(',')[-1] if ',' in str(b) else b)
    p.write_bytes(raw)
    print('QR salvo em:', p)
" 2>/dev/null || true

state=$(api "${BASE}/instance/connectionState/${INSTANCE}" 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get('instance',{}).get('state') or d.get('state') or 'unknown')
except Exception:
    print('unknown')
" 2>/dev/null || echo "unknown")

echo ""
echo "Done."
echo "  Manager UI: ${BASE}/manager  (instância: ${INSTANCE})"
echo "  Estado:     ${state}  (open = conectado; close/connecting = escanear QR)"
echo "  Webhook:    ${WEBHOOK_URL}"
echo "  Test parse: ./scripts/evi-test evolution"
if [ "$state" != "open" ]; then
  echo ""
  echo "  Próximo passo: abra o Manager → ${INSTANCE} → Conectar → escaneie o QR no WhatsApp."
fi
if [ -n "$EVI_KEY" ]; then
  echo "  Note: webhook headers include X-Api-Key (EVI_API_KEY set)."
else
  echo "  Note: EVI_API_KEY empty — /webhooks/evolution accepts requests without header."
fi
