"""Tools to review and confirm pending WhatsApp commitments."""

from __future__ import annotations

from typing import List, Optional

from langchain_core.tools import tool
from services.write_guard import guarded_write

from services.commitment_review.digest import format_pending_digest
from services.response_format import format_confirm_results
from tools.calendar_time import iso_event_range
from tools.calendar_tool import schedule_event_result
from tools.task_tool import create_task_result


def pending_rows(limit: int = 20) -> list:
    """Pending commitments (after the optional Evolution-log replay); shared by the tool
    (marked text for the model) and the direct list command (clean text for the user)."""
    import os

    from db import init_db, list_pending_commitments as _list

    if os.getenv("EVI_COMMITMENT_REPLAY_ON_LIST", "true").lower() in (
        "1",
        "true",
        "yes",
    ):
        from services.commitment_replay import replay_commitments_from_evolution_log

        days = int(os.getenv("EVI_COMMITMENT_REPLAY_DAYS", "14"))
        replay_commitments_from_evolution_log(days=days)

    init_db()
    return _list(limit=limit)


def scheduled_today_rows(limit: int = 25) -> list:
    from db import init_db, list_scheduled_today as _list_today

    init_db()
    rows = _list_today(limit=limit)
    for r in rows:
        for k in ("created_at", "confirmed_at"):
            if r.get(k):
                r[k] = str(r[k])
    return rows


@tool
def list_pending_commitments(limit: int = 20) -> str:
    """List pending commitments queued from WhatsApp (not yet on calendar)."""
    rows = pending_rows(limit)
    if not rows:
        return "Nenhum compromisso pendente."
    return format_pending_digest(rows)


@tool
def list_scheduled_today(limit: int = 25) -> str:
    """List commitments scheduled today with source chat and confirmation channel."""
    from services.commitment_review.digest import format_scheduled_today

    return format_scheduled_today(scheduled_today_rows(limit))


def _merge_briefing_ids(
    commitment_ids: Optional[List[int]], briefing_items: Optional[List[int]]
) -> tuple[List[int], List[str]]:
    ids = [int(c) for c in (commitment_ids or [])]
    errors: List[str] = []
    if briefing_items:
        from services.briefing import NO_BRIEFING_TODAY, resolve_briefing_items

        resolved, errors = resolve_briefing_items(list(briefing_items))
        if errors == [NO_BRIEFING_TODAY]:
            # Sem briefing hoje os números só podem ser ids do digest de pendentes
            # ("confirmar 1,2"); confirm/dismiss validam o id contra os pendentes.
            resolved, errors = [int(n) for n in briefing_items], []
        ids += [i for i in resolved if i not in ids]
    return ids, errors


@tool
@guarded_write
def confirm_commitments(
    commitment_ids: Optional[List[int]] = None,
    confirmed_via: str = "chat",
    briefing_items: Optional[List[int]] = None,
) -> str:
    """
    Confirm selected pending commitments: events → Google Calendar, tasks → Google Tasks.
    Marks rows as scheduled on success.
    If the user refers to numbers from the last briefing ('confirma 2', 'dispensa 1 e 3'),
    pass them in briefing_items — never as commitment_ids. Otherwise (ids from
    list_pending_commitments, or the commitment named by title) use commitment_ids and
    leave briefing_items empty. Never guess numbers: if the user named a commitment by
    title, call list_pending_commitments first to get its id.
    """
    from db import init_db, list_pending_commitments, update_commitment_status

    init_db()
    commitment_ids, resolve_errors = _merge_briefing_ids(commitment_ids, briefing_items)
    pending = {r["id"]: r for r in list_pending_commitments(limit=100, include_past=True)}
    results = list(resolve_errors)
    for cid in commitment_ids:
        row = pending.get(int(cid))
        if not row:
            results.append(f"#{cid}: not found or not pending")
            continue
        if row["type"] == "task":
            out = create_task_result(
                title=row["title"],
                due_date=row.get("due_date") or row.get("event_date") or "",
                notes=(row.get("raw_text") or "")[:500],
            )
            if out.ok:
                update_commitment_status(
                    int(cid), "scheduled", confirmed_via=confirmed_via
                )
                results.append(f"#{cid}: {out}")
            else:
                results.append(f"#{cid}: failed — {str(out)[:200]}")
            continue
        if row["type"] != "event":
            results.append(f"#{cid}: unsupported type {row['type']}")
            continue
        start, end = iso_event_range(row.get("event_date"), row.get("event_time"))
        out = schedule_event_result(
            title=row["title"],
            start_time=start,
            end_time=end,
            description=(row.get("raw_text") or "")[:500],
        )
        if out.ok:
            update_commitment_status(
                int(cid), "scheduled", confirmed_via=confirmed_via
            )
            results.append(f"#{cid}: {str(out)[:120]}")
        else:
            results.append(f"#{cid}: failed — {str(out)[:200]}")
    return format_confirm_results("\n".join(results))


@tool
@guarded_write
def dismiss_commitments(
    commitment_ids: Optional[List[int]] = None,
    briefing_items: Optional[List[int]] = None,
) -> str:
    """Dismiss pending commitments without scheduling.
    If the user refers to numbers from the last briefing ('confirma 2', 'dispensa 1 e 3'),
    pass them in briefing_items — never as commitment_ids. Otherwise (ids from
    list_pending_commitments, or the commitment named by title) use commitment_ids and
    leave briefing_items empty.
    """
    from db import init_db, update_commitment_status

    init_db()
    commitment_ids, errors = _merge_briefing_ids(commitment_ids, briefing_items)
    n = 0
    for cid in commitment_ids:
        if update_commitment_status(int(cid), "dismissed"):
            n += 1
    msg = f"Dismissed {n} commitment(s)."
    return "\n".join([msg, *errors]) if errors else msg
