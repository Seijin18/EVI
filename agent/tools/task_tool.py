from langchain_core.tools import tool

from tools.windmill_client import post_windmill


@tool
def create_task(title: str, due_date: str = "", notes: str = "") -> str:
    """
    Create a Google Task via Windmill script/webhook.
    """
    payload = {
        "action": "create_task",
        "title": title,
        "due_date": due_date,
        "notes": notes,
    }
    result = post_windmill(
        "WINDMILL_WEBHOOK_TASKS",
        payload,
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/create_task",
    )
    if "failed" in result.lower():
        return f"Failed to create task. {result}"
    return f"Successfully passed task '{title}' to Windmill. {result}"
