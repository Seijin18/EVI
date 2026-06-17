import os

from langchain_core.tools import tool

from integrations.factory import get_integration
from services.response_format import format_task_result


@tool
def create_task(title: str, due_date: str = "", notes: str = "") -> str:
    """
    Create a Google Task via the configured orchestration backend.
    """
    gtasks = os.getenv("WINDMILL_GTASKS_RESOURCE", "gtasks").strip()
    if gtasks.startswith("$var:"):
        gtasks = gtasks[5:]
    if gtasks and not gtasks.startswith("$res:"):
        gtasks = f"$res:{gtasks}"
    payload = {
        "title": title,
        "due_date": due_date,
        "notes": notes,
        "gtasks": gtasks,
    }
    result = get_integration().post("create_task", payload, timeout=180, wait_result=True)
    return format_task_result(title, result)
