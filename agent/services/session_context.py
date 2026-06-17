"""Session tool snapshots and JID extraction for context assembly."""

from __future__ import annotations

import json
import re
from typing import Any

_SNAPSHOT_TOOLS = frozenset(
    {
        "summarize_inbox",
        "delete_emails",
        "delete_emails_by_query",
        "list_pending_commitments",
        "list_scheduled_today",
    }
)


def extract_jid_from_session(session_id: str) -> str | None:
    if session_id.startswith("whatsapp-"):
        return session_id[len("whatsapp-") :]
    return None


def format_tool_snapshots(session_id: str, limit: int = 3) -> str:
    try:
        from db import init_db, load_tool_snapshots

        init_db()
        rows = load_tool_snapshots(session_id, limit=limit)
    except Exception:
        return ""
    if not rows:
        return ""
    lines = ["SESSION TOOL SNAPSHOTS (use for follow-ups):"]
    for row in rows:
        name = row.get("tool_name", "")
        payload = row.get("payload") or {}
        preview = json.dumps(payload, ensure_ascii=False)[:1200]
        lines.append(f"- {name}: {preview}")
    return "\n".join(lines)


def persist_tool_snapshots(session_id: str, output_messages: list[Any]) -> list[dict]:
    """Extract tool results from LangGraph messages and save to Postgres."""
    saved: list[dict] = []
    try:
        from db import init_db, save_tool_snapshot

        init_db()
    except Exception:
        return saved

    for msg in output_messages:
        msg_type = getattr(msg, "type", None)
        if msg_type != "tool":
            continue
        name = getattr(msg, "name", "") or ""
        if name not in _SNAPSHOT_TOOLS:
            continue
        raw = str(getattr(msg, "content", "") or "")
        payload: dict[str, Any]
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                payload = {"raw": raw[:2000]}
        except (json.JSONDecodeError, TypeError):
            payload = {"raw": raw[:2000]}
        try:
            save_tool_snapshot(session_id, name, payload)
            saved.append({"tool": name, "preview": raw[:200]})
        except Exception:
            pass
    return saved


def summarize_tool_calls(output_messages: list[Any]) -> list[dict]:
    """Audit-friendly tool call + result list."""
    summary: list[dict] = []
    for msg in output_messages:
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
