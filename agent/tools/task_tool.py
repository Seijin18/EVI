import os

from langchain_core.tools import tool

from tools.windmill_client import post_windmill


@tool
def create_task(title: str, due_date: str = "", notes: str = "") -> str:
    """
    Create a Google Task via Windmill script/webhook.
    """
    gtasks = os.getenv("WINDMILL_GTASKS_RESOURCE", "gtasks").strip()
    if not gtasks.startswith("$res:"):
        gtasks = f"$res:{gtasks}"
    payload = {
        "action": "create_task",
        "title": title,
        "due_date": due_date,
        "notes": notes,
        "gtasks": gtasks,
    }
    result = post_windmill(
        "WINDMILL_WEBHOOK_TASKS",
        payload,
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/create_task",
        timeout=180,
        wait_result=True,
    )
    if "failed" in result.lower():
        return f"Failed to create task. {result}"
    if '"status":"created"' in result or '"status": "created"' in result:
        return f"Task '{title}' created. {result}"
    if '"status":"error"' in result or '"status": "error"' in result:
        return f"Tasks error for '{title}'. {result}"
    return f"Windmill task job finished for '{title}'. {result}"
