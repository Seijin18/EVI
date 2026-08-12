import os
import re

from langchain_core.tools import tool

from integrations.factory import get_integration
from services.tool_result import ToolResult, parse_windmill_result
from tools.calendar_time import evi_timezone, normalize_wall_clock


def _calendar_payload(extra: dict) -> dict:
    gcal = os.getenv("WINDMILL_GCAL_RESOURCE", "gcal").strip()
    if gcal.startswith("$var:"):
        gcal = gcal[5:]
    if gcal and not gcal.startswith("$res:"):
        gcal = f"$res:{gcal}"
    calendar_id = os.getenv("WINDMILL_CALENDAR_ID", "primary").strip() or "primary"
    payload = {"gcal": gcal, "calendar_id": calendar_id, "timezone": evi_timezone()}
    payload.update(extra)
    return payload


def _gcal_resource() -> str:
    gcal = os.getenv("WINDMILL_GCAL_RESOURCE", "gcal").strip()
    if gcal.startswith("$var:"):
        gcal = gcal[5:]
    if gcal and not gcal.startswith("$res:"):
        gcal = f"$res:{gcal}"
    return gcal


def schedule_event_result(
    title: str, start_time: str, end_time: str, description: str = ""
) -> ToolResult:
    """Structured form of `schedule_event`, for callers that must branch on success.

    `confirm_commitments` gates a DB write on this — reading the prose instead is
    what let a failure containing "criada" mark a commitment as scheduled.
    """
    payload = {
        "action": "schedule_event",
        "title": title,
        "start_time": normalize_wall_clock(start_time),
        "end_time": normalize_wall_clock(end_time),
        "description": description,
        "gcal": _gcal_resource(),
        "calendar_id": os.getenv("WINDMILL_CALENDAR_ID", "primary").strip() or "primary",
        "timezone": evi_timezone(),
    }
    raw = get_integration().post("schedule_event", payload, timeout=180, wait_result=True)
    out = parse_windmill_result(
        raw,
        action=f"agendar '{title}'",
        resource_env="WINDMILL_GCAL_RESOURCE",
    )
    if not out.ok:
        return out

    link = (out.data or {}).get("html_link") or ""
    if not link:
        # The body can be truncated by the client before it parses; the link is
        # still worth scraping so the user gets something actionable.
        m = re.search(r'"html_link"\s*:\s*"([^"]+)"', raw)
        link = m.group(1) if m else ""
    message = f"Evento '{title}' criado no Google Calendar."
    if link:
        message += f"\nLink: {link}"
    return ToolResult.success(message, data=out.data)


@tool
def schedule_event(
    title: str, start_time: str, end_time: str, description: str = ""
) -> str:
    """
    Schedule a Google Calendar event via the configured orchestration backend.

    Args:
        title: Event title.
        start_time: Local wall clock (e.g. 2026-06-10T09:00:00) in EVI_TIMEZONE.
        end_time: Local wall clock end time.
        description: Optional description.
    """
    return str(schedule_event_result(title, start_time, end_time, description))


@tool
def list_calendar_events(
    days_ahead: int = 7,
    limit: int = 25,
    on_date: str = "",
) -> str:
    """
    List upcoming Google Calendar events in EVI_TIMEZONE.

    Args:
        days_ahead: Calendar days to include from today (1=today only, 2=today+tomorrow, default 7).
        limit: Maximum events to return (default 25).
        on_date: Optional YYYY-MM-DD — list only that calendar day (use CALENDAR LOOKUP TABLE for "amanhã").
    """
    extra: dict = {
        "days_ahead": days_ahead,
        "max_results": limit,
    }
    if (on_date or "").strip():
        extra["on_date"] = on_date.strip()[:10]
    payload = _calendar_payload(extra)
    raw = get_integration().post("list_events", payload, timeout=120, wait_result=True)
    out = parse_windmill_result(
        raw, action="listar eventos", resource_env="WINDMILL_GCAL_RESOURCE"
    )
    if not out.ok:
        return str(out)

    blob = out.data or {}
    events = blob.get("events") or []
    if not events:
        od = blob.get("on_date")
        if od:
            return f"Nenhum evento em {od}."
        return f"Nenhum evento nos próximos {days_ahead} dia(s) de calendário."

    lines = [f"Próximos eventos ({blob.get('count', len(events))}):"]
    for ev in events:
        title = ev.get("summary") or "(sem título)"
        when = ev.get("start") or "?"
        link = ev.get("html_link") or ""
        line = f"• {when} — {title}"
        if link:
            line += f"\n  {link}"
        lines.append(line)
    return "\n".join(lines)


@tool
def list_calendars() -> str:
    """
    List Google calendars available to EVI (summary + calendar id).
    Use when configuring WINDMILL_CALENDAR_ID or user asks which calendars exist.
    """
    raw = get_integration().post(
        "list_calendars", {"gcal": _gcal_resource()}, timeout=60, wait_result=True
    )
    out = parse_windmill_result(
        raw, action="listar calendários", resource_env="WINDMILL_GCAL_RESOURCE"
    )
    if not out.ok:
        return str(out)
    cals = (out.data or {}).get("calendars") or []
    if not cals:
        return "Nenhum calendário encontrado na conta Google."
    lines = ["Calendários Google:"]
    for c in cals:
        summary = c.get("summary") or "(sem nome)"
        cid = c.get("id") or "?"
        lines.append(f"• {summary}\n  id: {cid}")
    return "\n".join(lines)
