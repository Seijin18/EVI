"""Trim JSONL audit logs to a maximum age and line count."""

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


def trim_jsonl(
    path: Path,
    *,
    max_age_days: int | None = None,
    max_lines: int | None = None,
) -> int:
    """Drop lines older than max_age_days and/or keep only the newest max_lines."""
    if not path.exists():
        return 0
    days = max_age_days if max_age_days is not None else int(
        os.getenv("EVI_LOG_MAX_AGE_DAYS", "7")
    )
    line_cap = max_lines
    if line_cap is None:
        env_cap = os.getenv("EVI_LOG_MAX_LINES", "").strip()
        if env_cap.isdigit():
            line_cap = int(env_cap)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    original = path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    removed = 0
    for line in original:
        if not line.strip():
            removed += 1
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
    if line_cap is not None and len(kept) > line_cap:
        overflow = len(kept) - line_cap
        kept = kept[-line_cap:]
        removed += overflow
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


def prune_harness_logs(log_dir: Path, *, max_age_days: int | None = None) -> int:
    """Remove old evi-test harness logs (whatsapp_*.jsonl, logs/harness/*)."""
    days = max_age_days if max_age_days is not None else int(
        os.getenv("EVI_HARNESS_LOG_MAX_AGE_DAYS", "1")
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    patterns = ["whatsapp_*.jsonl"]
    dirs = [log_dir, log_dir / "harness"]
    for directory in dirs:
        if not directory.exists():
            continue
        for pattern in patterns:
            for path in directory.glob(pattern):
                try:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    continue
                if mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
        if directory.name == "harness" and directory.exists() and not any(directory.iterdir()):
            try:
                directory.rmdir()
            except OSError:
                pass
    return removed


def prune_logs(log_dir: Path) -> dict[str, int]:
    """Run retention on production and harness logs."""
    stats: dict[str, int] = {"harness_removed": 0}
    stats["harness_removed"] = prune_harness_logs(log_dir)
    evolution = log_dir / "evolution_webhook.jsonl"
    if evolution.exists():
        stats["evolution_trimmed"] = trim_jsonl(
            evolution,
            max_lines=int(os.getenv("EVI_LOG_MAX_LINES", "5000") or "5000"),
        )
    telegram = log_dir / "telegram.jsonl"
    if telegram.exists():
        stats["telegram_trimmed"] = trim_jsonl(telegram)
    return stats
