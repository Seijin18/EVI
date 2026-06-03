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
    payload = {
        "action": "schedule_event",
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "description": description,
    }
    result = post_windmill(
        "WINDMILL_WEBHOOK_CALENDAR",
        payload,
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/schedule_event",
    )
    if "failed" in result.lower():
        return f"Failed to schedule event. {result}"
    return f"Successfully passed the event '{title}' to Windmill. {result}"
