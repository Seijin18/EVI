"""Pre-compaction memory flush to daily log files."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.workspace import append_daily_memory


def flush_session_turn(
    session_id: str,
    user_text: str,
    assistant_text: str,
    tool_summary: list[dict] | None = None,
) -> bool:
    """Append a compact line to memory/YYYY-MM-DD.md before history trim."""
    ts = datetime.now(timezone.utc).strftime("%H:%M")
    tools_bit = ""
    if tool_summary:
        names = [t.get("tool", "") for t in tool_summary if t.get("tool")]
        if names:
            tools_bit = f" tools={','.join(names[:5])}"
    line = (
        f"- [{ts}] session={session_id} user={user_text[:120]!r} "
        f"assistant={assistant_text[:120]!r}{tools_bit}"
    )
    return append_daily_memory(line)


def maybe_flush_before_compaction(
    *,
    session_id: str,
    messages: list[Any],
    user_text: str,
    assistant_text: str,
    tool_summary: list[dict] | None = None,
) -> None:
    """Called when bounded memory is about to drop old turns."""
    if not user_text.strip():
        return
    flush_session_turn(session_id, user_text, assistant_text, tool_summary)
