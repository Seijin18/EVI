"""Trim JSONL audit logs to a maximum age."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def trim_jsonl(path: Path, *, max_age_days: int | None = None) -> int:
    """Drop lines older than max_age_days. Returns number of lines removed."""
    if not path.exists():
        return 0
    days = max_age_days if max_age_days is not None else int(
        os.getenv("EVI_LOG_MAX_AGE_DAYS", "7")
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept: list[str] = []
    removed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            removed += 1
            continue
        ts = _parse_ts(str(entry.get("ts", "")))
        if ts is None or ts >= cutoff:
            kept.append(line)
        else:
            removed += 1
    if removed:
        path.write_text(
            ("\n".join(kept) + "\n") if kept else "",
            encoding="utf-8",
        )
    return removed


def append_jsonl(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
