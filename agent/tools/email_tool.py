import os
from typing import List

from langchain_core.tools import tool

from integrations.factory import get_integration
from services.response_format import (
    format_delete_emails_result,
    format_inbox_result,
)


def _gmail_resource() -> str:
    gmail = os.getenv("WINDMILL_GMAIL_RESOURCE", "gmail").strip()
    if gmail.startswith("$var:"):
        gmail = gmail[5:]
    if gmail and not gmail.startswith("$res:"):
        gmail = f"$res:{gmail}"
    return gmail


@tool
def summarize_inbox(max_messages: int = 10) -> str:
    """
    Summarize recent Gmail INBOX messages via Windmill OAuth.
    Returns subject, sender and message id for each email.
    """
    payload = {
        "max_messages": max_messages,
        "gmail": _gmail_resource(),
    }
    result = get_integration().post("summarize_inbox", payload, timeout=180, wait_result=True)
    return format_inbox_result(result)


@tool
def delete_emails(message_ids: List[str]) -> str:
    """
    Move Gmail messages to trash by message id (from summarize_inbox).

    Args:
        message_ids: One or more Gmail message IDs.
    """
    ids = [str(i).strip() for i in message_ids if str(i).strip()]
    if not ids:
        return "Informe pelo menos um id de email (ex.: ids retornados por summarize_inbox)."
    payload = {
        "message_ids": ids,
        "gmail": _gmail_resource(),
    }
    result = get_integration().post("delete_emails", payload, timeout=120, wait_result=True)
    return format_delete_emails_result(result, count=len(ids))
