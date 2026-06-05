"""Append-only audit log for Telegram chat turns."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List


def _log_path() -> Path:
    base = Path(os.getenv("EVI_LOG_DIR", "/logs"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "telegram.jsonl"


def _tool_summary(messages: List[Any]) -> List[dict]:
    if messages and isinstance(messages[0], dict) and "tool" in messages[0]:
        return list(messages)
    summary: List[dict] = []
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "ai" and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                summary.append({"kind": "call", "tool": name})
        if msg_type == "tool":
            name = getattr(msg, "name", "")
            content = str(getattr(msg, "content", ""))[:500]
            summary.append({"kind": "result", "tool": name, "preview": content})
    return summary


def log_telegram_turn(
    session_id: str,
    user_text: str,
    response_text: str,
    output_messages: List[Any],
    *,
    telegram_sent: bool,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "user": user_text[:2000],
        "assistant": response_text[:2000],
        "tools": _tool_summary(output_messages),
        "telegram_sent": telegram_sent,
    }
    path = _log_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
