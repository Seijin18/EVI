"""Claude Code CLI dev-bridge backend."""

from __future__ import annotations

from pathlib import Path

from devcli.base import DevCliResult
from devcli.runner_common import run_script

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "claude-dev-runner.sh"


class ClaudeCliBackend:
    name = "claude"

    def run(
        self, mode: str, description: str, *, repo_root: Path, timeout_sec: int
    ) -> DevCliResult:
        return run_script(
            _SCRIPT, mode, description, repo_root=repo_root, timeout_sec=timeout_sec
        )
