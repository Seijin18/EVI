## Why

The dev bridge (`dev: <desc>` / `dev approve <id>` on WhatsApp/Telegram control chat) shipped hardcoded to the Cursor Agent CLI, and `approve_dev_task` always invoked `cursor-dev-runner.sh plan` — a read-only mode — so approving a job never actually applied code changes. The user no longer uses Cursor and wants Claude Code CLI as the default backend, with the ability to add other CLIs later without touching the core propose/approve logic.

## What Changes

- New `agent/devcli/` package: `Protocol` (`DevCliBackend`/`DevCliResult`) + factory (`get_dev_cli`/`resolve_dev_cli`, `EVI_DEV_CLI` env var) mirroring `agent/integrations/`'s pattern. Adding a CLI backend later is one new module + one factory branch.
- `agent/devcli/claude_backend.py` + `scripts/claude-dev-runner.sh`: Claude Code CLI backend (`plan`/`apply`/`review`), default (`EVI_DEV_CLI=claude`). `apply` runs `--permission-mode acceptEdits`, commits on a per-job `dev/job-*` branch, and prints `EVI_DEV_BRANCH=`/`EVI_DEV_DIFFSTAT=` markers so results are never silently discarded.
- **Bug fix**: `approve_dev_task` now resolves the job's backend and calls `.run("apply", ...)` — real edits happen on approval instead of a no-op plan.
- `dev_jobs` gains `backend`/`mode`/`branch` columns; new `dev_bridge_state` key-value table backs a `dev mode plan|default` chat toggle (eager plan preview on propose vs lazy registration only — mirrors Claude Code's own `/plan` toggle).
- `try_dev_command` grammar extended additively: `--cli=<name>` override on `dev:`/`dev approve`, plus `dev mode [plan|default]`. The 3 original command shapes and the `str | None` contract are unchanged.
- Cursor (`scripts/cursor-dev-runner.sh`) and Copilot (`scripts/copilot-dev-runner.sh`) are left as-is, unwired, for now — out of scope for this change, addable later as `agent/devcli/` modules without touching this change's core.

## Impact

`agent/services/dev_bridge.py`, `agent/devcli/` (new), `agent/db.py`, `agent/tools/dev_bridge_tool.py`, `scripts/claude-dev-runner.sh` (new), `tests/unit/test_dev_bridge.py`, `tests/unit/test_devcli_*.py` (new), `openspec/specs/dev-bridge` (new domain spec).
