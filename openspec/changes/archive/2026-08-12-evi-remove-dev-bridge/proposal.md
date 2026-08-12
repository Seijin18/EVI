## Why

BACKLOG #33 asked: fix the dev bridge or remove it. The decision is **remove**.

It has never worked in the containerised deployment. `_REPO_ROOT =
Path(__file__).resolve().parents[2]` resolves to `/` inside the image
(`WORKDIR /app` + `COPY . .`), `scripts/` is not in the image, and neither `git`
nor the `claude` CLI is installed — so `dev approve <id>` has always returned
`claude-dev-runner.sh missing`. It shipped as Done on 1 Aug 2026 and nobody
noticed for six weeks because every test mocks the backend. The container smoke
(#32) now prints it as `[KNOWN]` on every run.

Making it work would mean mounting the repo writable into `agent-api` and
installing a code-editing CLI there, with the trust boundary being a WhatsApp
JID from a webhook payload that is unauthenticated by default. That is a large
security surface for a capability `ssh` already covers, and there is no usage
habit to preserve — the feature has never once executed successfully.

## What Changes

- **Removed**: `agent/services/dev_bridge.py`, `agent/devcli/` (base, factory,
  runner_common, claude_backend), `agent/tools/dev_bridge_tool.py` and its two
  registry entries, `scripts/{claude,cursor,copilot}-dev-runner.sh`,
  `openspec/specs/dev-bridge/`, `.cursor/rules/evi-dev-bridge.mdc`,
  `docs/dev-workflow.md`, and the four test files.
- **Call sites**: `whatsapp_control.process_whatsapp_control_message` and
  `telegram_handler` drop the `try_dev_command` branch, so a `dev: ...` message
  now falls through to the LLM like any other text. `graph.SYSTEM_PROMPT` rule 10
  loses its dev-bridge clause.
- **Env**: `EVI_DEV_BRIDGE_ENABLED`, `EVI_DEV_CLI`,
  `EVI_DEV_BRIDGE_TIMEOUT_SEC` removed from `.env.example`.
- **Database**: the `CREATE TABLE` statements for `dev_jobs` and
  `dev_bridge_state` and their six accessor functions are removed from
  `agent/db.py`. Existing installs keep two empty tables — `dev_jobs` has 0 rows
  here — because a `DROP TABLE` in a migration is destructive for no benefit.
  Documented rather than executed.
- **Harness**: `evi-test dev-bridge` goes, and with it one entry from
  `run_smoke`'s list, so offline smoke becomes **13/13**. That count is hardcoded
  in `README.md`, `Progress.md`, `docs/testing.md` and
  `openspec/specs/testing/spec.md`; all four are updated.
- **Container smoke**: the `[KNOWN]` exemption for the dev-bridge modules is
  deleted, so the import-time path assertion becomes unconditional again.

## Impact

`agent/services/dev_bridge.py`, `agent/devcli/`, `agent/tools/dev_bridge_tool.py`,
`agent/tools/registry.py`, `agent/db.py`, `agent/graph.py`,
`agent/services/whatsapp_control.py`, `agent/services/telegram_handler.py`,
`agent/testing/cli.py`, `agent/testing/container_checks.py`, `scripts/`,
`.env.example`, `README.md`, `Progress.md`, `docs/testing.md`, `CLAUDE.md`,
`openspec/AGENTS.md`.
Specs: `dev-bridge` (removed), `testing` (13/13).

Out of scope: dropping the two orphan tables, and any replacement for remote
code execution. If it is ever wanted again, the archived changes
(`2026-06-03-dev-assistant-bridge`, `2026-08-01-evi-dev-bridge-multi-cli`)
retain the full design.
