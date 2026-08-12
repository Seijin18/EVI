## Why

The `container` job added in `evi-container-smoke-ci` fails on `main`. It also had
a side effect nobody would want.

`docker-compose.yml` reaches outside the compose project in **four** independent
ways, and `-p evi-smoke` isolates none of them. The previous change fixed two and
asserted isolation in its spec — an assertion that was not true:

| Channel | Consequence | Fixed in |
|---|---|---|
| bind mounts (`./data`) | corrupted the dev Postgres on 2026-08-12 | #32 |
| published ports | collided with the running dev stack | #32 |
| `env_file: - .env` | **CI red; a second Telegram poller against the real bot** | here |
| `.env` variable interpolation | `WINDMILL_TOKEN`, `NEO4J_PASSWORD` still leaked | here |

In CI there is no `.env`, so `docker compose config` exits 1 with
`env file .../.env not found`; the isolation guard saw empty output and aborted.
The guard did its job — it failed safe — but the smoke never ran there once.

Locally it is worse: the smoke inherited the real `GEMINI_API_KEY`,
`TELEGRAM_BOT_TOKEN`, `EVOLUTION_API_KEY`, `EVI_WHATSAPP_CONTROL_JIDS` and
`TELEGRAM_MODE=polling`, so its throwaway `agent-api` started a **second poller on
the live bot**. The dev agent-api log carries 25 `HTTP Error 409: Conflict`
clustered between 08:42 and 09:00, exactly across the smoke runs. Telegram hands
`getUpdates` to one poller and 409s the other, so real messages could have been
consumed by a container that was about to be deleted.

## What Changes

- `docker-compose.smoke.yml`: `env_file: !reset []` on `agent-api`.
- `scripts/evi-container-smoke.sh` runs compose with `--env-file /dev/null`.
  Resetting `env_file` alone was **not** enough: Compose also reads `./.env` for
  `${VAR}` interpolation, which is a separate channel, and `WINDMILL_TOKEN` /
  `NEO4J_PASSWORD` still arrived. Verified both before and after.
- The smoke exports `TELEGRAM_MODE=`, `TELEGRAM_BOT_TOKEN=`, `TELEGRAM_CHAT_ID=`,
  `EVI_WHATSAPP_CONTROL_JIDS=`, `EVOLUTION_API_KEY=`, `GEMINI_API_KEY=` empty, so a
  future isolation regression still cannot start a poller.
- **The isolation guard is rewritten to check the consequence, not the mechanism.**
  The first version tested `svc.get("env_file")` — but `docker compose config`
  resolves `env_file` into `environment` and drops the key, so that check silently
  always passed. It reported `[PASS]` against a config that was actively leaking.
  It now asserts no real credential appears in any service's resolved
  `environment`, and that `TELEGRAM_MODE` is empty.

## Impact

`docker-compose.smoke.yml`, `scripts/evi-container-smoke.sh`.
Specs: `testing` (the isolation requirement gains the two missing channels and the
consequence-based assertion).

No agent code changes; no behaviour change outside the smoke.
