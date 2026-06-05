import os

from langchain_core.tools import tool

from tools.windmill_client import post_windmill


@tool
def schedule_event(
    title: str, start_time: str, end_time: str, description: str = ""
) -> str:
    """
    Schedule a Google Calendar event via Windmill script/webhook.

    Args:
        title: Event title.
        start_time: ISO 8601 start (e.g. 2026-06-10T14:00:00Z).
        end_time: ISO 8601 end.
        description: Optional description.
    """
    gcal = os.getenv("WINDMILL_GCAL_RESOURCE", "gcal").strip()
    if gcal.startswith("$var:"):
        gcal = gcal[5:]
    if gcal and not gcal.startswith("$res:"):
        gcal = f"$res:{gcal}"
    calendar_id = os.getenv("WINDMILL_CALENDAR_ID", "primary").strip() or "primary"
    payload = {
        "action": "schedule_event",
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "description": description,
        "gcal": gcal,
        "calendar_id": calendar_id,
    }
    result = post_windmill(
        "WINDMILL_WEBHOOK_CALENDAR",
        payload,
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/schedule_event",
        timeout=180,
        wait_result=True,
    )
    if "failed" in result.lower():
        return f"Failed to schedule event. {result}"
    if '"status":"created"' in result or '"status": "created"' in result:
        return f"Event '{title}' created in Google Calendar. {result}"
    if '"status":"error"' in result or '"status": "error"' in result:
        return f"Calendar error for '{title}'. {result}"
    return f"Windmill job finished for '{title}'. {result}"
