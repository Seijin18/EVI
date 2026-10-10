"""Seed the sim agent's EVI_WORKSPACE with the versioned bootstrap files.

The sim container's workspace starts empty, so the production bootstrap files
(AGENTS.md, TOOLS.md, ...) never reached the simulated system prompt. After the runner
wipes the workspace we copy ``git ls-files EVI_WORKSPACE/`` (minus personal files) into it,
plus the fictitious ``tests/sim/workspace/USER.md``. A copy, not a mount: isolation holds.
"""

from __future__ import annotations

import fnmatch
import io
import subprocess
import tarfile
from pathlib import Path

WORKSPACE_PREFIX = "EVI_WORKSPACE/"
SELECTED = ("AGENTS.md", "TOOLS.md", "HEARTBEAT.md", "skills/*/SKILL.md")
PERSONAL = {"USER.md", "MEMORY.md"}


def select_workspace_files(paths: list[str]) -> list[str]:
    """Pure: from repo-relative paths (``git ls-files`` output) keep the versioned,
    non-personal workspace files; returns paths relative to the workspace root."""
    out: list[str] = []
    for p in paths:
        p = p.strip()
        if not p.startswith(WORKSPACE_PREFIX):
            continue
        rel = p[len(WORKSPACE_PREFIX):]
        if rel in PERSONAL or rel.split("/")[-1] in PERSONAL:
            continue
        if any(fnmatch.fnmatchcase(rel, pat) for pat in SELECTED):
            out.append(rel)
    return sorted(out)


def build_tar(root: Path, sim_dir: Path) -> bytes:
    """Tar of the versioned workspace files plus the fictitious sim workspace files."""
    ls = subprocess.run(
        ["git", "ls-files", WORKSPACE_PREFIX], cwd=root, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for rel in select_workspace_files(ls):
            tar.add(root / WORKSPACE_PREFIX / rel, arcname=rel)
        if sim_dir.is_dir():
            for f in sorted(sim_dir.rglob("*")):
                if f.is_file():
                    tar.add(f, arcname=str(f.relative_to(sim_dir)))
    return buf.getvalue()
