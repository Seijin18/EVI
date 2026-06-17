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
EVI_TIMEZONE=America/Sao_Paulo
```

Horários são **relógio local** (`09:00` = 9h em `EVI_TIMEZONE`), não UTC. Após mudar o script, rode `../scripts/wmill-sync.sh`.

Resource OAuth atual após reconectar: confira com `wmill resource list`.

**Token frio / 422 na primeira chamada:** Windmill pode renovar o OAuth do resource (`gcal`, `gtasks`, `gmail`) só após o primeiro acesso. O agent repete automaticamente uma vez (`EVI_WINDMILL_RETRY_ATTEMPTS=2`, pausa `EVI_WINDMILL_RETRY_DELAY_SEC=2`).

## Google Tasks (`create_task`)

O EVI chama `create_task` → Windmill → Google Tasks API usando o resource em `WINDMILL_GTASKS_RESOURCE` (parâmetro `gtasks` no script).

**Importante:** o OAuth **`gcloud` do Windmill não é Google Tasks.** O conector `gcloud` pede só `https://www.googleapis.com/auth/cloud-platform` (tela “dados do Google Cloud”). Colocar escopos Tasks no Google Cloud Console **não muda** o que o Windmill pede na autorização.

### Opção recomendada — OAuth custom `gtasks` (CE self-hosted)

1. **Google Cloud Console** — Tasks API habilitada; escopos `tasks` no consent screen; redirect:
   ```
   http://localhost:8001/oauth/callback/gtasks
   ```
2. **Windmill Instance settings → OAuth** — adicione cliente **`gtasks`** (mesmo Client ID/Secret do `gcal`) com `connect_config`:
   ```json
   "gtasks": {
     "id": "SEU_CLIENT_ID.apps.googleusercontent.com",
     "secret": "SEU_CLIENT_SECRET",
     "connect_config": {
       "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
       "token_url": "https://oauth2.googleapis.com/token",
       "scopes": ["https://www.googleapis.com/auth/tasks"],
       "extra_params": { "access_type": "offline", "prompt": "consent" }
     }
   }
   ```
   (No CE, edite o JSON de OAuth na instância — padrão usado para Keycloak/custom providers.)
3. **Workspace `evi` → Resources** → tipo **`gtasks`** → Connect → Google deve pedir **“Criar, editar, organizar e excluir tarefas”**.
4. `.env`: `WINDMILL_GTASKS_RESOURCE=u/<user>/<nome_do_resource>`
5. `docker compose up -d agent-api` e `./scripts/evi-test tasks --live-windmill`

Não use resource `gcloud`/`equitable_gcloud` para Tasks — o token terá escopo Cloud Platform e a API retorna 403.

Verificação:

```bash
./scripts/evi-test tasks              # offline fixture
./scripts/evi-test tasks --live-windmill   # SCN-TASK-05 — cria task real
```

## Gmail (`summarize_inbox`, `delete_emails`)

**Importante:** o conector Gmail padrão do Windmill costuma pedir só `gmail.send` (enviar). Ler inbox e apagar exige escopos extras **no OAuth do Windmill**, não só no Google Cloud Console.

### Configurar OAuth `gmail` no Windmill (CE self-hosted)

1. **Google Cloud Console** — Gmail API habilitada; escopos no consent screen:
   - `https://www.googleapis.com/auth/gmail.readonly` (ler)
   - `https://www.googleapis.com/auth/gmail.modify` (ler + lixeira)
   - Redirect: `http://localhost:8001/oauth/callback/gmail`
2. **Windmill Instance settings → OAuth** — edite/adicione cliente **`gmail`** com `connect_config`:
   ```json
   "gmail": {
     "id": "SEU_CLIENT_ID.apps.googleusercontent.com",
     "secret": "SEU_CLIENT_SECRET",
     "connect_config": {
       "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
       "token_url": "https://oauth2.googleapis.com/token",
       "scopes": [
         "https://www.googleapis.com/auth/gmail.readonly",
         "https://www.googleapis.com/auth/gmail.modify"
       ],
       "extra_params": { "access_type": "offline", "prompt": "consent" }
     }
   }
   ```
3. **Workspace `evi` → Resources** → **`my_gmail`** → **Disconnect** → **Connect** de novo.
   Na tela Google deve aparecer permissão de **ler** e **modificar** e-mails (não só enviar).
4. `.env`: `WINDMILL_GMAIL_RESOURCE=u/<user>/my_gmail` — compose usa `env_file: .env`.
5. `docker compose up -d --force-recreate agent-api`

Verificar escopos do token armazenado:

```bash
docker compose exec agent-api python3 -c "
import json, os, urllib.request, urllib.parse
path = os.environ['WINDMILL_GMAIL_RESOURCE']
# ... (ou rode ./scripts/evi-test email --live-windmill)
"
./scripts/evi-test email --live-windmill
```

Comandos diretos no Telegram/WhatsApp: «verifique minha caixa de entrada do gmail», «apagar email \<id\>».

Verificação:

```bash
./scripts/evi-test email              # offline fixture
./scripts/evi-test email --live-windmill   # SCN-EMAIL-05 — summary real
```

## Telegram (`telegram_to_evi` + digest)

### Modo polling (recomendado em casa — sem domínio nem tunnel)

1. `.env`: `TELEGRAM_MODE=polling`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
2. `./scripts/evi-telegram-polling-setup.sh` — remove webhook e sobe poller no `agent-api`.
3. Mensagens: `getUpdates` → agent → `sendMessage`. Digest de compromissos continua igual.
4. **Logs:** `logs/telegram.jsonl` (turnos + tools usadas), Postgres `messages` com `session_id=telegram-<chat_id>`.

### Modo webhook (remoto via tunnel)

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
