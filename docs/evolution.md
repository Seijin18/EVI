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

## Grupo whitelist (ingest de compromissos)

1. No WhatsApp, abra o grupo e copie o JID de `logs/evolution_webhook.jsonl` (`sender` em linhas `filtered_out` com `reason: group`) ou use o Manager.
2. Defina no `.env`: `EVI_WHATSAPP_GROUP_WHITELIST=120363012345678901@g.us`
3. Rode `./scripts/setup-evolution.sh` (define `groupsIgnore=false` quando whitelist não vazia).
4. `docker compose up -d agent-api`

## Canal de controle EVI (chat + digest)

Para conversar com a EVI e receber digest de pendentes **no WhatsApp** (sem ack no chat de origem):

| Variável | Exemplo |
|----------|---------|
| `EVI_WHATSAPP_CONTROL_JIDS` | `5511999999999@s.whatsapp.net` (Mensagens para mim) ou JID de grupo só seu |
| `EVI_NOTIFY_CHANNELS` | `telegram,whatsapp` |
| `EVI_WHATSAPP_REPLY_PREFIX` | `[EVI] ` (padrão) |

Suas mensagens no JID de controle vão para `/chat` e comandos de review (`listar pendentes`, `confirmar 1`, `agendados hoje`). Respostas da EVI saem com prefixo `[EVI]` e não reentram no pipeline de ingest.

## Aprendizado sobre contato (backfill)

Quando você pede *"aprenda sobre Leozao nos últimos 30 dias"*, o EVI:

1. Resolve o contato por **nome ou telefone** (sem JID)
2. Chama Evolution `POST /chat/findMessages/{instance}` para ler mensagens em cache
3. Grava na timeline do contato (`EVI_CONTACT_MEMORY_DIR`) e sintetiza o perfil (LLM)

| Variável | Padrão | Efeito |
|----------|--------|--------|
| `EVI_BACKFILL_MAX_MESSAGES` | 200 | Máximo de mensagens por importação |
| `EVI_BACKFILL_INCLUDE_FROM_ME` | true | Inclui suas respostas na timeline (`[eu] ...`) |

**Limite:** a Evolution só devolve o que está no **banco local** da instância. Com `syncFullHistory: false` (padrão do `setup-evolution.sh`), chats antigos podem não existir — nesse caso aumente o histórico na instância ou troque mensagens recentes com o contato para popular o cache.
