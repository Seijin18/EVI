# Windmill (EVI orchestration)

Replaces n8n. Scripts live under `windmill/f/` for `wmill sync`.

## Postgres (first time on existing volume)

If Windmill restarts with `role "windmill_admin" does not exist`:

```bash
./scripts/fix-windmill-postgres.sh
```

## Workspace

Create workspace `evi` in Windmill UI (http://localhost:8001) or via CLI.

## Scripts (import paths)

| Script | Purpose | Env on agent-api |
|--------|---------|------------------|
| `f/integrations/schedule_event` | Google Calendar | `WINDMILL_WEBHOOK_CALENDAR` |
| `f/integrations/create_task` | Google Tasks | `WINDMILL_WEBHOOK_TASKS` |
| `f/integrations/summarize_inbox` | Gmail summary | `WINDMILL_WEBHOOK_EMAIL` |
| `f/integrations/telegram_to_evi` | Forward Telegram → agent-api | `WINDMILL_WEBHOOK_TELEGRAM` |

Expose each script as **HTTP trigger** and paste URL into `.env`.

## OAuth

Configure Google/Gmail credentials as Windmill **Resources** once; scripts read them.

## Install CLI (`wmill: command not found` / crash on Node 18)

`windmill-cli` **requires Node.js 20+**. Pop!_OS often ships Node 18 as default; `getRandomValues` errors mean you need a newer Node.

```bash
nvm use 22          # or: nvm install 22
# If nvm complains about ~/.npmrc prefix: nvm use --delete-prefix v22.22.3
node -v             # must show v20+
npm install -g windmill-cli
wmill --version
```

Ensure `~/.npm-global/bin` (or wherever npm -g installs) is in your `PATH`.

From repo (auto-switches nvm when available):

```bash
./scripts/install-wmill.sh
# run any wmill command with correct Node:
../scripts/wmill.sh workspace switch evi
```

This folder has `.nvmrc` → `22`.

## Token + workspace (once)

**User API token** (CLI, `WINDMILL_TOKEN`, Bearer no agent):

1. UI http://localhost:8001 → barra lateral **ícone de pessoa** (perfil) → **Account settings** (não é Workspace settings).
2. Seção **Tokens** → label → **New token** → copie na hora (só aparece uma vez).

Alternativa CLI (com Node 22 no PATH): `wmill user create-token` ou `wmill token create --label evi`.

**Webhook do script** (sem token global): abra `f/integrations/schedule_event` → **Details and Triggers** → URL Async (pode incluir `?token=…`).

Depois, from this folder:

```bash
cd ~/Projects/EVI/windmill
wmill workspace add evi evi http://localhost:8001 --token 'SEU_TOKEN'
wmill workspace switch evi
wmill folder add-missing -y
wmill generate-metadata
../scripts/wmill-sync.sh
```

`wmill.yaml` already maps workspace `evi` → `http://localhost:8001`.

## HTTP triggers (after push)

Open each script under `f/integrations/*` → **Details and Triggers** → copy **Async** URL into `.env` (`WINDMILL_WEBHOOK_*`).

The URL **must** include auth: append `?token=…` (webhook-specific token from the same tab) or set `WINDMILL_TOKEN` and use `Authorization: Bearer` (see `.env.example`). A bare `/jobs/run/p/...` path returns **401 Unauthorized**.

## Google Calendar (`schedule_event`)

1. Instance **Settings → OAuth** → add **gcal** (redirect `http://localhost:8001/oauth/callback/gcal`).
2. Workspace **Resources** → connect resource named **gcal** (path often `u/<user>/gcal`).
3. In the script editor, set parameter **gcal** default to that resource path if not literally `gcal`.
4. `../scripts/wmill-sync.sh`, then run once in the UI with test times — confirm event in Google Calendar.

### Calendário dedicado "EVI"

O script usa `calendar_id` (env `WINDMILL_CALENDAR_ID` no agent). O nome **EVI** só funciona se o OAuth tiver escopo `calendar.readonly` para listar calendários; caso contrário use o **Calendar ID** completo:

Google Calendar → calendário **EVI** → ⚙️ Settings → **Integrate calendar** → **Calendar ID** (ex. `abc123@group.calendar.google.com`).

```env
WINDMILL_GCAL_RESOURCE=u/shiba144/beneficial_gcal
WINDMILL_CALENDAR_ID=SEU_CALENDAR_ID_AQUI
```

Resource OAuth atual após reconectar: confira com `wmill resource list`.

## Google Tasks (`create_task`)

Windmill não tem conector nativo Tasks; use resource **gcloud** com escopo OAuth `https://www.googleapis.com/auth/tasks`.

1. Instance **Settings → OAuth** → add **gcloud** (redirect `http://localhost:8001/oauth/callback/gcloud`).
2. Ao conectar, inclua escopo **Google Tasks API** (ou reconecte resource existente com Tasks habilitado).
3. Workspace **Resources** → path ex. `u/<user>/gcloud` — copie para `.env` como `WINDMILL_GTASKS_RESOURCE`.
4. Script `create_task` → parâmetro **gtasks** default = esse path (ou nome `gtasks` se renomear resource).
5. HTTP trigger → `WINDMILL_WEBHOOK_TASKS` no `.env`; `../scripts/wmill-sync.sh`.

Verificação:

```bash
./scripts/evi-test tasks              # offline fixture
./scripts/evi-test tasks --live-windmill   # SCN-TASK-05 — cria task real
```

## Gmail (`summarize_inbox`)

1. Instance **Settings → OAuth** → add **gmail** (redirect `http://localhost:8001/oauth/callback/gmail`).
2. Workspace **Resources** → connect **gmail** (path ex. `u/<user>/gmail`).
3. `.env`: `WINDMILL_GMAIL_RESOURCE=u/<user>/gmail` no agent-api (compose já repassa).
4. HTTP trigger do script → `WINDMILL_WEBHOOK_EMAIL`.

Verificação:

```bash
./scripts/evi-test email              # offline fixture
./scripts/evi-test email --live-windmill   # SCN-EMAIL-05 — summary real
```

## Telegram (`telegram_to_evi` + digest)

1. **@BotFather** → token; `getUpdates` ou @userinfobot → `TELEGRAM_CHAT_ID` no `.env`.
2. **Salve** `.env` e `docker compose up -d --force-recreate agent-api`.
3. Script `f/integrations/telegram_to_evi` → **Triggers** → **+ Add trigger → HTTP** (path: `f/integrations/telegram_to_evi`).
4. URL do trigger (formato `/api/r/`):

   `http://localhost:8001/api/r/f/integrations/telegram_to_evi?token=WEBHOOK_TOKEN`

   No `.env`: `WINDMILL_TELEGRAM_WEBHOOK_TOKEN`, `WINDMILL_WEBHOOK_TELEGRAM` com path `/api/r/...`.

5. Workspace **evi** → **Variables**: `EVI_AGENT_URL=http://agent-api:8000/webhooks/telegram`, `EVI_API_KEY` (opcional).
6. `cd windmill && echo y | ../scripts/wmill.sh sync push --workspace evi`
7. **Chat remoto (dev):** `./scripts/telegram-tunnel-setup.sh` — trycloudflare (URL muda a cada restart).
8. **Chat remoto (estável, gratuito):** Cloudflare named tunnel — defina no `.env`:
   `CLOUDFLARE_TUNNEL_NAME=evi-windmill`, `CLOUDFLARE_TUNNEL_HOSTNAME=wm.seudominio.com`
   (domínio no Cloudflare Free). Uma vez: `cloudflared tunnel login`, `tunnel create`, `tunnel route dns`.
   Depois: `./scripts/cloudflared-tunnel-setup.sh`

O script aceita body **cru** do Telegram (`update_id` + `message` na raiz). O agent responde via `sendMessage` (`telegram_sent: true`).

Verificação local (sem webhook público):

```bash
./scripts/evi-telegram-verify.sh
```

## RAM note

Server + one worker ~512MB each; disable extra workers on 16GB hosts.
