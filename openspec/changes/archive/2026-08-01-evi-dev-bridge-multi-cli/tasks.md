## 1. Implementation

- [x] 1.1 `devcli` Protocol + factory + runner_common
  - Files: `agent/devcli/base.py`, `agent/devcli/factory.py`, `agent/devcli/runner_common.py`
  - Verify: `tests/unit/test_devcli_factory.py`, `tests/unit/test_runner_common.py`

- [x] 1.2 Claude Code CLI backend
  - Files: `agent/devcli/claude_backend.py`, `scripts/claude-dev-runner.sh`
  - Verify: `tests/unit/test_devcli_claude_backend.py`

- [x] 1.3 Fix approve bug + backend/mode/branch persistence
  - Files: `agent/services/dev_bridge.py`, `agent/db.py`
  - Verify: `tests/unit/test_dev_bridge.py::test_approve_dev_task_uses_apply_mode`

- [x] 1.4 `dev mode plan|default` toggle + `--cli=` overrides
  - Files: `agent/services/dev_bridge.py`, `agent/db.py` (`dev_bridge_state`)
  - Verify: `tests/unit/test_dev_bridge.py::test_propose_dev_task_mode_toggle`, `::test_try_dev_command_cli_override_parsing`

- [x] 1.5 Tool + env + docs
  - Files: `agent/tools/dev_bridge_tool.py`, `.env.example`, `docs/dev-workflow.md`, `.cursor/rules/evi-dev-bridge.mdc`
  - Verify: manual read-through

- [x] 1.6 Spec delta
  - Files: `openspec/changes/evi-dev-bridge-multi-cli/specs/dev-bridge/spec.md`
  - Verify: `openspec validate evi-dev-bridge-multi-cli`
