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

1. UI http://localhost:8001 → **Workspace settings** → **Tokens** → Create token.
2. From this folder:

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

## RAM note

Server + one worker ~512MB each; disable extra workers on 16GB hosts.
