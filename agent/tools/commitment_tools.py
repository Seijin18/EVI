"""Tools to review and confirm pending WhatsApp commitments."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List

from langchain_core.tools import tool

from tools.calendar_tool import schedule_event
from tools.task_tool import create_task


def _iso_range(event_date: str | None, event_time: str | None) -> tuple[str, str]:
    date = event_date or datetime.utcnow().strftime("%Y-%m-%d")
    time = event_time or "12:00"
    if len(time) == 5:
        start = datetime.strptime(f"{date}T{time}:00", "%Y-%m-%dT%H:%M:%S")
    else:
        start = datetime.strptime(f"{date}T12:00:00", "%Y-%m-%dT%H:%M:%S")
    end = start + timedelta(hours=1)
    return (
        start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


@tool
def list_pending_commitments(limit: int = 20) -> str:
    """List pending commitments queued from WhatsApp (not yet on calendar)."""
    from db import init_db, list_pending_commitments

    init_db()
    rows = list_pending_commitments(limit=limit)
    if not rows:
        return "No pending commitments."
    for r in rows:
        r["created_at"] = str(r.get("created_at", ""))
    return json.dumps(rows, ensure_ascii=False, indent=2)


@tool
def confirm_commitments(commitment_ids: List[int]) -> str:
    """
    Confirm selected pending commitments: events → Google Calendar, tasks → Google Tasks.
    Marks rows as scheduled on success.
    """
    from db import init_db, list_pending_commitments, update_commitment_status

    init_db()
    pending = {r["id"]: r for r in list_pending_commitments(limit=100)}
    results = []
    for cid in commitment_ids:
        row = pending.get(int(cid))
        if not row:
            results.append(f"#{cid}: not found or not pending")
            continue
        if row["type"] == "task":
            out = create_task.invoke(
                {
                    "title": row["title"],
                    "due_date": row.get("due_date") or row.get("event_date") or "",
                    "notes": (row.get("raw_text") or "")[:500],
                }
            )
            if "created" in out.lower():
                update_commitment_status(int(cid), "scheduled")
                results.append(f"#{cid}: {out[:120]}")
            else:
                results.append(f"#{cid}: failed — {out[:200]}")
            continue
        if row["type"] != "event":
            results.append(f"#{cid}: unsupported type {row['type']}")
            continue
        start, end = _iso_range(row.get("event_date"), row.get("event_time"))
        out = schedule_event.invoke(
            {
                "title": row["title"],
                "start_time": start,
                "end_time": end,
                "description": (row.get("raw_text") or "")[:500],
            }
        )
        if "created" in out.lower():
            update_commitment_status(int(cid), "scheduled")
            results.append(f"#{cid}: {out[:120]}")
        else:
            results.append(f"#{cid}: failed — {out[:200]}")
    return "\n".join(results)


@tool
def dismiss_commitments(commitment_ids: List[int]) -> str:
    """Dismiss pending commitments without scheduling."""
    from db import init_db, update_commitment_status

    init_db()
    n = 0
    for cid in commitment_ids:
        if update_commitment_status(int(cid), "dismissed"):
            n += 1
    return f"Dismissed {n} commitment(s)."
