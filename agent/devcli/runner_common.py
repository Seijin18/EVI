"""Shared subprocess execution for dev-bridge CLI runner scripts."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from devcli.base import DevCliResult

_BRANCH_RE = re.compile(r"^EVI_DEV_BRANCH=(.*)$", re.MULTILINE)
_DIFFSTAT_RE = re.compile(r"^EVI_DEV_DIFFSTAT=(.*)$", re.MULTILINE)


def _runs_dir(repo_root: Path) -> Path:
    raw = os.getenv("EVI_WORKSPACE", "").strip()
    base = Path(raw) if raw else repo_root / "EVI_WORKSPACE"
    d = base / "dev-runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_apply_markers(stdout: str) -> tuple[str, str]:
    branch_m = _BRANCH_RE.search(stdout)
    diff_m = _DIFFSTAT_RE.search(stdout)
    return (
        branch_m.group(1).strip() if branch_m else "",
        diff_m.group(1).strip() if diff_m else "",
    )


def run_script(
    script: Path,
    mode: str,
    description: str,
    *,
    repo_root: Path,
    timeout_sec: int,
) -> DevCliResult:
    if not script.is_file():
        return DevCliResult(exit_code=1, stderr=f"{script.name} missing")

    log_path = _runs_dir(repo_root) / (
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{mode}.log"
    )
    cmd = [str(script), mode, description]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ, "EVI_REPO_ROOT": str(repo_root)},
        )
        log_path.write_text(
            proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8"
        )
        branch, diff_stat = (
            _parse_apply_markers(proc.stdout) if mode == "apply" else ("", "")
        )
        return DevCliResult(
            exit_code=proc.returncode,
            stdout=proc.stdout[:4000],
            stderr=proc.stderr[:1000],
            log_path=str(log_path),
            branch=branch,
            diff_stat=diff_stat,
        )
    except subprocess.TimeoutExpired:
        return DevCliResult(
            exit_code=124, stderr="timeout", log_path=str(log_path)
        )
    except Exception as exc:
        return DevCliResult(exit_code=1, stderr=str(exc)[:300])
