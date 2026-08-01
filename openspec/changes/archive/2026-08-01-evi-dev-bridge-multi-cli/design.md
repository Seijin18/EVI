## Design

- `agent/devcli/base.py`: `Protocol DevCliBackend` (`name`, `run(mode, description, *, repo_root, timeout_sec) -> DevCliResult`); `DevCliResult` dataclass (`exit_code`, `stdout`, `stderr`, `log_path`, `branch`, `diff_stat`).
- `agent/devcli/runner_common.py`: shared `run_script()` — subprocess with timeout, timestamped log in `EVI_WORKSPACE/dev-runs/`, parses `EVI_DEV_BRANCH=`/`EVI_DEV_DIFFSTAT=` stdout markers for apply-mode results. One implementation shared by every backend module.
- `agent/devcli/factory.py`: `resolve_dev_cli(name)` (uncached, used for per-job `--cli=` overrides) and `get_dev_cli()` (`@lru_cache(1)`, reads `EVI_DEV_CLI`, delegates to `resolve_dev_cli`) — same shape as `agent/integrations/factory.py`.
- `scripts/claude-dev-runner.sh apply`: creates `dev/job-<ts>` branch, runs `claude -p "$DESC" --permission-mode acceptEdits --output-format text`, commits any diff, prints the branch/diffstat markers. Never merges — the branch is left for manual review.
- Approval stays chat-command-only (`dev approve <id>`); no LangGraph tool can trigger `apply` itself, preserving the human-in-the-loop gate.
- `dev_bridge_state` is a generic `(key, value)` table so future toggles (not just `propose_mode`) don't need new tables.

## Out of scope

- Cursor worktree→branch reconciliation and Copilot's `plan`/`apply` compatibility shim (both CLIs are unwired for now).
- An agent-invokable approve tool.
- Persisted per-job default CLI beyond the explicit `--cli=` override.
