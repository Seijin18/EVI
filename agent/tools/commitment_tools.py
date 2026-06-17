"""Tools to review and confirm pending WhatsApp commitments."""

from __future__ import annotations

from typing import List

from langchain_core.tools import tool

from services.commitment_review.digest import format_pending_digest
from services.response_format import format_confirm_results
from tools.calendar_time import iso_event_range
from tools.calendar_tool import schedule_event
from tools.task_tool import create_task


def _tool_succeeded(out: str) -> bool:
    low = out.lower()
    return "created" in low or "criado" in low


@tool
def list_pending_commitments(limit: int = 20) -> str:
    """List pending commitments queued from WhatsApp (not yet on calendar)."""
    from db import init_db, list_pending_commitments as _list

    init_db()
    rows = _list(limit=limit)
    if not rows:
        return "Nenhum compromisso pendente."
    return format_pending_digest(rows)


@tool
def list_scheduled_today(limit: int = 25) -> str:
    """List commitments scheduled today with source chat and confirmation channel."""
    from db import init_db, list_scheduled_today as _list_today
    from services.commitment_review.digest import format_scheduled_today

    init_db()
    rows = _list_today(limit=limit)
    for r in rows:
        for k in ("created_at", "confirmed_at"):
            if r.get(k):
                r[k] = str(r[k])
    return format_scheduled_today(rows)


@tool
def confirm_commitments(
    commitment_ids: List[int],
    confirmed_via: str = "chat",
) -> str:
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
            if _tool_succeeded(out):
                update_commitment_status(
                    int(cid), "scheduled", confirmed_via=confirmed_via
                )
                results.append(f"#{cid}: {out}")
            else:
                results.append(f"#{cid}: failed — {out[:200]}")
            continue
        if row["type"] != "event":
            results.append(f"#{cid}: unsupported type {row['type']}")
            continue
        start, end = iso_event_range(row.get("event_date"), row.get("event_time"))
        out = schedule_event.invoke(
            {
                "title": row["title"],
                "start_time": start,
                "end_time": end,
                "description": (row.get("raw_text") or "")[:500],
            }
        )
        if _tool_succeeded(out):
            update_commitment_status(
                int(cid), "scheduled", confirmed_via=confirmed_via
            )
            results.append(f"#{cid}: {out[:120]}")
        else:
            results.append(f"#{cid}: failed — {out[:200]}")
    return format_confirm_results("\n".join(results))


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
