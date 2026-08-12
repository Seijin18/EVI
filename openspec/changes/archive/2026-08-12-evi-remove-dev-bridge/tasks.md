## 1. Implementation

- [x] 1.1 Drop the call sites so nothing imports the bridge
  - SCN-DEVX-01
  - Files: `agent/services/whatsapp_control.py`, `agent/services/telegram_handler.py`, `agent/graph.py`, `agent/tools/registry.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_control.py tests/unit/test_telegram_handler.py -q`

- [x] 1.2 Delete the modules, scripts and tests
  - SCN-DEVX-01
  - Files: `agent/services/dev_bridge.py`, `agent/devcli/`, `agent/tools/dev_bridge_tool.py`, `scripts/*-dev-runner.sh`, `tests/unit/test_dev_bridge.py`, `tests/unit/test_devcli_*.py`, `tests/unit/test_runner_common.py`
  - Verify: `grep -rn "dev_bridge\|devcli" agent/ tests/ scripts/` returns nothing

- [x] 1.3 Remove the tables' DDL and accessors (no DROP — see design)
  - SCN-DEVX-02
  - Files: `agent/db.py`
  - Verify: `grep -n "dev_jobs\|dev_bridge_state" agent/db.py` returns nothing

- [x] 1.4 Harness: drop the subcommand, smoke becomes 13/13
  - SCN-E2E-02
  - Files: `agent/testing/cli.py`, `agent/testing/container_checks.py`
  - Verify: `./scripts/evi-test smoke` reports 13/13

- [x] 1.5 Docs and env
  - Files: `.env.example`, `README.md`, `Progress.md`, `docs/testing.md`, `CLAUDE.md`, `openspec/AGENTS.md`, `.cursor/rules/evi-dev-bridge.mdc`, `docs/dev-workflow.md`
  - Verify: `grep -rn "dev bridge\|dev-bridge" README.md Progress.md docs/ CLAUDE.md` only mentions the removal

- [x] 1.6 Delete the `dev-bridge` spec; update `testing` to 13/13
  - Files: `openspec/specs/dev-bridge/` (deleted), `openspec/changes/evi-remove-dev-bridge/{removed-spec-dev-bridge.md,specs/testing/spec.md}`
  - Note: archive cannot delta-remove a whole spec (empty spec fails validation) — see design.
  - Verify: `openspec validate evi-remove-dev-bridge`

## 2. Close-out

- [x] 2.1 Full gate green
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-test smoke && ./scripts/evi-container-smoke.sh && ruff check agent/ --select E,W,F --ignore E501 && openspec validate --specs`

- [x] 2.2 Update `Progress.md` + `openspec/BACKLOG.md` (#33 → Done/removed), then `openspec archive evi-remove-dev-bridge`
  - Files: `Progress.md`, `openspec/BACKLOG.md`
  - Verify: `openspec list` empty
