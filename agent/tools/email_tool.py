import os

from langchain_core.tools import tool

from integrations.factory import get_integration


@tool
def summarize_inbox(max_messages: int = 10) -> str:
    """
    Request inbox summary via the configured orchestration backend.
    """
    gmail = os.getenv("WINDMILL_GMAIL_RESOURCE", "gmail").strip()
    if not gmail.startswith("$res:"):
        gmail = f"$res:{gmail}"
    payload = {
        "max_messages": max_messages,
        "gmail": gmail,
    }
    result = get_integration().post("summarize_inbox", payload, timeout=180, wait_result=True)
    if "failed" in result.lower():
        return f"Failed to summarize inbox. {result}"
    if '"status":"ok"' in result or '"summary"' in result:
        return f"Inbox summary: {result}"
    return f"Inbox summary: {result}"
