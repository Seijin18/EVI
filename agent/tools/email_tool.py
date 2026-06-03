from langchain_core.tools import tool

from tools.windmill_client import post_windmill


@tool
def summarize_inbox(max_messages: int = 10) -> str:
    """
    Request inbox summary via Windmill (Gmail credentials stored in Windmill resources).
    """
    payload = {"action": "summarize_inbox", "max_messages": max_messages}
    result = post_windmill(
        "WINDMILL_WEBHOOK_EMAIL",
        payload,
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/summarize_inbox",
    )
    if "failed" in result.lower():
        return f"Failed to summarize inbox. {result}"
    return f"Inbox summary: {result}"
