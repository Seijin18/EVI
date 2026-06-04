# Evolution API (WhatsApp) — EVI

## Stack

| Componente | URL |
|------------|-----|
| Evolution (host) | http://localhost:8082 |
| Manager | http://localhost:8082/manager |
| Webhook → EVI | `http://agent-api:8000/webhooks/evolution` (rede Docker) |

## Configuração automática

```bash
./scripts/setup-evolution.sh
```

Cria a instância `evi` (se não existir), aponta webhook para o agent e mostra como obter o QR.

Variáveis em `.env`:

- `EVOLUTION_API_KEY` — header `apikey` (igual ao compose)
- `EVOLUTION_SERVER_URL` — http://localhost:8082
- `EVOLUTION_INSTANCE_NAME` — padrão `evi`
- `EVOLUTION_WEBHOOK_URL` — padrão URL interna do agent

## Conectar WhatsApp

1. Abra http://localhost:8082/manager
2. Instância **evi** → **Conectar** → escanear QR (o endpoint `/instance/connect` pode retornar `count: 0`; o QR aparece no Manager)
3. Estado `open` em `./scripts/setup-evolution.sh` ou API `GET /instance/connectionState/evi`
4. Envie uma mensagem de teste; confira **`logs/evolution_webhook.jsonl` no host** (volume `./logs` → `/logs` no container) ou `./scripts/evi-test evolution`

Se o arquivo não existir no host mas o webhook responder 200, verifique logs antigos: `docker exec evi-agent-api-1 tail /tmp/evi-logs/evolution_webhook.jsonl` (antes do volume) ou recrie o `agent-api` após atualizar o compose.

### QR não aparece (Manager vazio ou `count: 0`)

A imagem **`atendai/evolution-api:v2.1.1`** costuma entrar em loop (`statusReason 405`) sem QR. O compose usa **`evoapicloud/evolution-api:v2.3.7`**.

```bash
docker compose pull evolution-api
docker compose up -d --force-recreate evolution-api
./scripts/setup-evolution.sh --reset
```

Abra http://localhost:8082/manager ou escaneie `logs/evolution_qr.png` se o script gerar o arquivo.

## Compose

`docker-compose.yml` já define webhook global e `AUTHENTICATION_API_KEY`. O script garante webhook **por instância** (necessário na v2).

## EVI_API_KEY

Se definir `EVI_API_KEY` no `.env`, o script envia `X-Api-Key` no webhook da Evolution. Sem chave, o endpoint `/webhooks/evolution` fica aberto na rede Docker.

## Filtrar volume de mensagens

Na primeira conexão a Evolution pode enviar **muitas** mensagens antigas. Duas camadas de filtro:

**Evolution (fonte)** — `./scripts/setup-evolution.sh` define:
- `syncFullHistory: false` — não baixar histórico completo
- `groupsIgnore: true` — ignorar grupos na instância
- Webhook só com evento `MESSAGES_UPSERT`

**EVI (webhook)** — variáveis no `.env`:

| Variável | Padrão | Efeito |
|----------|--------|--------|
| `EVI_WHATSAPP_MAX_PER_WEBHOOK` | 10 | No máximo N mensagens **mais recentes** por payload |
| `EVI_WHATSAPP_MAX_AGE_HOURS` | 24 | Ignora mensagens mais antigas que X horas |
| `EVI_WHATSAPP_INCOMING_ONLY` | true | Ignora mensagens enviadas por você (`fromMe`) |
| `EVI_WHATSAPP_SKIP_GROUPS` | true | Ignora chats `@g.us` |
| `EVI_WHATSAPP_DEDUPE_IDS` | true | Não reprocessa o mesmo `message id` |

O log inclui `"step": "filter"` com contadores (`received`, `kept`, `skipped_old`, etc.).

IDs já vistos ficam em `logs/evolution_seen_ids.json`. Para reprocessar tudo: apague esse arquivo e reinicie só se necessário.

Depois de mudar filtros: `docker compose up -d agent-api` e opcionalmente `./scripts/setup-evolution.sh` (sem `--reset`) para atualizar settings na Evolution.
