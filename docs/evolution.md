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
4. Envie uma mensagem de teste; confira `logs/evolution_webhook.jsonl` ou `./scripts/evi-test evolution`

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
