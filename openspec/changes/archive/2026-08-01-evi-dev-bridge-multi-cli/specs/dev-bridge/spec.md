## ADDED Requirements

### Requirement: Pluggable dev CLI backend
The system SHALL resolve the dev-bridge CLI backend via a `Protocol` + factory (`agent/devcli/`), selectable through `EVI_DEV_CLI` (default `claude`) or a per-job `--cli=<name>` override. Adding a new backend SHALL require only a new module implementing `DevCliBackend` plus one branch in `resolve_dev_cli`, with no changes to `agent/services/dev_bridge.py`.

#### Scenario: SCN-DEV-01
- **WHEN** `tests/unit/test_devcli_factory.py` runs
- **THEN** `get_dev_cli()` returns the `claude` backend by default and `resolve_dev_cli("unknown")` raises `ValueError`

### Requirement: Approval applies real changes
When a dev job is approved (`dev approve <id>`), the system SHALL execute the resolved backend in `apply` mode — not `plan` — so file edits actually happen, committed on a per-job branch that is never merged automatically.

#### Scenario: SCN-DEV-02
- **WHEN** `tests/unit/test_dev_bridge.py::test_approve_dev_task_uses_apply_mode` runs
- **THEN** the backend's `run()` is invoked with `mode="apply"` and the job record stores `mode`, `backend`, and `branch`

### Requirement: Dev bridge gated to control chat
The dev bridge SHALL only be reachable when `EVI_DEV_BRIDGE_ENABLED=true`, from WhatsApp/Telegram control-chat messages, and approval SHALL remain a manual chat command — no LangGraph tool may trigger `apply` directly.

#### Scenario: SCN-DEV-03
- **WHEN** `EVI_DEV_BRIDGE_ENABLED` is unset or false
- **THEN** `propose_dev_task`/`approve_dev_task` return `ok: False` without invoking any CLI

### Requirement: Propose preview toggle
The system SHALL support toggling, via `dev mode plan` / `dev mode default` chat commands persisted in `dev_bridge_state`, whether proposing a task (`dev: <desc>`) eagerly runs a synchronous `plan`-mode preview or only registers the job (default).

#### Scenario: SCN-DEV-04
- **WHEN** `tests/unit/test_dev_bridge.py::test_propose_dev_task_mode_toggle` runs
- **THEN** `dev mode plan` and `dev mode default` update the persisted toggle and `dev mode` reports the current value
