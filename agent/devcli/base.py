"""Protocol interface for dev-bridge CLI backends (Claude Code, Cursor, ...)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class DevCliResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    log_path: str = ""
    branch: str = ""
    diff_stat: str = ""


@runtime_checkable
class DevCliBackend(Protocol):
    """Minimal surface every dev-bridge CLI backend must implement."""

    name: str

    def run(
        self,
        mode: str,
        description: str,
        *,
        repo_root: Path,
        timeout_sec: int,
    ) -> DevCliResult:
        """Execute description in the given mode ('plan' | 'apply' | 'review')."""
        ...
