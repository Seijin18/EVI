import os

from langchain_core.tools import tool

from integrations.factory import get_integration
from services.response_format import format_list_tasks_result, format_task_result


def _gtasks_resource() -> str:
    gtasks = os.getenv("WINDMILL_GTASKS_RESOURCE", "gtasks").strip()
    if gtasks.startswith("$var:"):
        gtasks = gtasks[5:]
    if gtasks and not gtasks.startswith("$res:"):
        gtasks = f"$res:{gtasks}"
    return gtasks


@tool
def create_task(title: str, due_date: str = "", notes: str = "") -> str:
    """
    Create a Google Task via the configured orchestration backend.
    """
    payload = {
        "title": title,
        "due_date": due_date,
        "notes": notes,
        "gtasks": _gtasks_resource(),
    }
    result = get_integration().post("create_task", payload, timeout=180, wait_result=True)
    return format_task_result(title, result)


@tool
def list_tasks(max_results: int = 25, show_completed: bool = False) -> str:
    """
    List open Google Tasks from the default task list.

    Args:
        max_results: Maximum tasks to return (default 25).
        show_completed: Include completed tasks (default false).
    """
    payload = {
        "gtasks": _gtasks_resource(),
        "max_results": max_results,
        "show_completed": show_completed,
    }
    result = get_integration().post("list_tasks", payload, timeout=120, wait_result=True)
    return format_list_tasks_result(result)
