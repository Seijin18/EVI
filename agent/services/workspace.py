"""EVI workspace paths (OpenClaw-style bootstrap files)."""

from __future__ import annotations

import os
from pathlib import Path

_BOOTSTRAP_FILES = ("USER.md", "AGENTS.md", "TOOLS.md", "MEMORY.md", "HEARTBEAT.md")
_MAX_FILE_CHARS = 4000


def workspace_root() -> Path:
    raw = os.getenv("EVI_WORKSPACE", "").strip()
    if raw:
        return Path(raw)
    project = os.getenv("EVI_PROJECT_ROOT", "").strip()
    if project:
        return Path(project) / "EVI_WORKSPACE"
    return Path(__file__).resolve().parents[2] / "EVI_WORKSPACE"


def read_bootstrap_file(name: str) -> str:
    path = workspace_root() / name
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) > _MAX_FILE_CHARS:
        return text[:_MAX_FILE_CHARS] + "\n… (truncated)"
    return text


def read_daily_memory(days_back: int = 1) -> str:
    from datetime import datetime, timedelta, timezone

    root = workspace_root() / "memory"
    if not root.is_dir():
        return ""
    lines: list[str] = []
    now = datetime.now(timezone.utc).date()
    for offset in range(days_back + 1):
        day = (now - timedelta(days=offset)).isoformat()
        path = root / f"{day}.md"
        if path.is_file():
            chunk = path.read_text(encoding="utf-8").strip()
            if chunk:
                lines.append(f"### {day}\n{chunk[:1500]}")
    return "\n\n".join(lines)


def append_daily_memory(line: str) -> bool:
    from datetime import datetime, timezone

    root = workspace_root() / "memory"
    try:
        root.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).date().isoformat()
        path = root / f"{day}.md"
        with path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
        return True
    except OSError:
        return False


def bootstrap_names() -> tuple[str, ...]:
    return _BOOTSTRAP_FILES
