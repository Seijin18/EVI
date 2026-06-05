import json
import os
import re

from langchain_core.tools import tool

from tools.calendar_time import evi_timezone, normalize_wall_clock
from tools.windmill_client import post_windmill


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


@tool
def schedule_event(
    title: str, start_time: str, end_time: str, description: str = ""
) -> str:
    """
    Schedule a Google Calendar event via Windmill script/webhook.

    Args:
        title: Event title.
        start_time: Local wall clock (e.g. 2026-06-10T09:00:00) in EVI_TIMEZONE.
        end_time: Local wall clock end time.
        description: Optional description.
    """
    gcal = os.getenv("WINDMILL_GCAL_RESOURCE", "gcal").strip()
    if gcal.startswith("$var:"):
        gcal = gcal[5:]
    if gcal and not gcal.startswith("$res:"):
        gcal = f"$res:{gcal}"
    calendar_id = os.getenv("WINDMILL_CALENDAR_ID", "primary").strip() or "primary"
    tz = evi_timezone()
    payload = {
        "action": "schedule_event",
        "title": title,
        "start_time": normalize_wall_clock(start_time),
        "end_time": normalize_wall_clock(end_time),
        "description": description,
        "gcal": gcal,
        "calendar_id": calendar_id,
        "timezone": tz,
    }
    result = post_windmill(
        "WINDMILL_WEBHOOK_CALENDAR",
        payload,
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/schedule_event",
        timeout=180,
        wait_result=True,
    )
    if "failed" in result.lower():
        return f"Falha ao agendar '{title}'. {result[:400]}"

    link = ""
    try:
        blob = json.loads(result) if result.strip().startswith("{") else None
        if blob is None:
            m = re.search(r'"html_link"\s*:\s*"([^"]+)"', result)
            link = m.group(1) if m else ""
        else:
            link = blob.get("html_link") or ""
    except (json.JSONDecodeError, TypeError):
        m = re.search(r'"html_link"\s*:\s*"([^"]+)"', result)
        link = m.group(1) if m else ""

    if '"status":"created"' in result or '"status": "created"' in result:
        if link:
            return f"Evento '{title}' criado no Google Calendar.\nLink: {link}"
        return f"Evento '{title}' criado no Google Calendar."
    if '"status":"error"' in result or '"status": "error"' in result:
        return f"Erro no Calendar para '{title}'. {result[:400]}"
    return f"Windmill finalizou '{title}'. {result[:400]}"


@tool
def list_calendar_events(days_ahead: int = 7, limit: int = 25) -> str:
    """
    List upcoming Google Calendar events in EVI_TIMEZONE.

    Args:
        days_ahead: Number of days ahead to search (default 7).
        limit: Maximum events to return (default 25).
    """
    payload = _calendar_payload(
        {
            "days_ahead": days_ahead,
            "max_results": limit,
        }
    )
    result = post_windmill(
        "WINDMILL_WEBHOOK_LIST_EVENTS",
        payload,
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/list_events",
        timeout=120,
        wait_result=True,
    )
    if "failed" in result.lower():
        return f"Falha ao listar eventos. {result[:400]}"

    try:
        blob = json.loads(result) if result.strip().startswith("{") else None
    except json.JSONDecodeError:
        blob = None

    if blob is None:
        return f"Resposta inesperada ao listar eventos. {result[:400]}"

    if blob.get("status") == "error":
        return f"Erro no Calendar: {blob.get('detail', result)[:400]}"

    events = blob.get("events") or []
    if not events:
        return f"Nenhum evento nos próximos {days_ahead} dias."

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
