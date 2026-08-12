## MODIFIED Requirements

### Requirement: Container smoke gates the composed system
CI SHALL run `scripts/evi-container-smoke.sh`, which builds the agent image, brings up `postgres`, `qdrant` and `agent-api` under an isolated compose project, and asserts the properties that only exist once the system is built and wired. It SHALL always tear the stack down, and SHALL NOT touch a developer's running stack, volumes, credentials or live channels. The same script SHALL be reachable locally as `./scripts/evi-test container`.

`docker-compose.yml` reaches outside the compose project in four ways that a project name does not isolate, and the smoke SHALL close all four:
- **bind mounts** under `./data` → redirected to named volumes;
- **published ports** → `!reset` / `!override` so a running dev stack keeps its own;
- **`env_file: - .env`** → `!reset []`, so the developer's real credentials never enter the smoke;
- **`.env` variable interpolation**, a channel independent of `env_file` → compose is invoked with `--env-file /dev/null`.

The smoke SHALL additionally export the channel variables (`TELEGRAM_MODE`, bot token, chat id, control JIDs, provider keys) empty, so that an isolation regression still cannot start a poller against the live bot.

The isolation guard SHALL assert the **consequence** — that no real credential appears in any service's resolved `environment`, and that `TELEGRAM_MODE` is empty — rather than the mechanism. Checking for an `env_file` key is specifically forbidden: `docker compose config` resolves it into `environment` and drops the key, so such a check silently always passes.

The assertions SHALL include:
- `GET /` and `GET /health` answer, and **every** `/health` check that is not `skipped` reports `ok: true` — the aggregate `status` alone is too coarse. Dependencies the smoke deliberately does not start (Windmill, Ollama) are named explicitly and reported as `[INFO]`, never fatal.
- `GET /tools` lists the whole registry, so a tool that cannot import inside the image fails the build.
- Every module-level path constant resolved from `__file__` at import time exists inside the image and is not `/`. No exemptions remain — the dev bridge, the only module that ever needed one, was removed.
- Every published port for a data service in `docker compose config` carries a host IP.
- A clean boot produces no `soft-fail` line and no traceback.

#### Scenario: SCN-CI-02
- **WHEN** `./scripts/evi-container-smoke.sh` runs on a clean checkout
- **THEN** it exits 0 with one `[PASS]` line per assertion, and the stack is removed afterwards even on failure

#### Scenario: SCN-CI-04
- **GIVEN** a checkout with **no** `.env` (the CI condition)
- **WHEN** the smoke runs
- **THEN** it exits 0 — it must not depend on a file that is gitignored
- **AND** with a real `.env` present it also exits 0, and `docker compose logs agent-api | grep -c 409` does not grow, proving no second Telegram poller started
- **AND** with the `env_file` reset removed, the guard aborts before building, naming the leaked variables
