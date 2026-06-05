import os

from langchain_core.tools import tool

from tools.windmill_client import post_windmill


@tool
def summarize_inbox(max_messages: int = 10) -> str:
    """
    Request inbox summary via Windmill (Gmail credentials stored in Windmill resources).
    """
    gmail = os.getenv("WINDMILL_GMAIL_RESOURCE", "gmail").strip()
    if not gmail.startswith("$res:"):
        gmail = f"$res:{gmail}"
    payload = {
        "max_messages": max_messages,
        "gmail": gmail,
    }
    result = post_windmill(
        "WINDMILL_WEBHOOK_EMAIL",
        payload,
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/summarize_inbox",
        timeout=180,
        wait_result=True,
    )
    if "failed" in result.lower():
        return f"Failed to summarize inbox. {result}"
    if '"status":"ok"' in result or '"summary"' in result:
        return f"Inbox summary: {result}"
    return f"Inbox summary: {result}"
