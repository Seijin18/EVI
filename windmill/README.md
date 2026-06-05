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
wmill sync push
```

`wmill.yaml` already maps workspace `evi` → `http://localhost:8001`.

## HTTP triggers (after push)

Open each script under `f/integrations/*` → **Details and Triggers** → copy **Async** URL into `.env` (`WINDMILL_WEBHOOK_*`).

The URL **must** include auth: append `?token=…` (webhook-specific token from the same tab) or set `WINDMILL_TOKEN` and use `Authorization: Bearer` (see `.env.example`). A bare `/jobs/run/p/...` path returns **401 Unauthorized**.

## Google Calendar (`schedule_event`)

1. Instance **Settings → OAuth** → add **gcal** (redirect `http://localhost:8001/oauth/callback/gcal`).
2. Workspace **Resources** → connect resource named **gcal** (path often `u/<user>/gcal`).
3. In the script editor, set parameter **gcal** default to that resource path if not literally `gcal`.
4. `wmill sync push`, then run once in the UI with test times — confirm event in Google Calendar.

### Calendário dedicado "EVI"

O script usa `calendar_id` (env `WINDMILL_CALENDAR_ID` no agent). O nome **EVI** só funciona se o OAuth tiver escopo `calendar.readonly` para listar calendários; caso contrário use o **Calendar ID** completo:

Google Calendar → calendário **EVI** → ⚙️ Settings → **Integrate calendar** → **Calendar ID** (ex. `abc123@group.calendar.google.com`).

```env
WINDMILL_GCAL_RESOURCE=u/shiba144/beneficial_gcal
WINDMILL_CALENDAR_ID=SEU_CALENDAR_ID_AQUI
```

Resource OAuth atual após reconectar: confira com `wmill resource list`.

## RAM note

Server + one worker ~512MB each; disable extra workers on 16GB hosts.
