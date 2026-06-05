"""Shared Telegram update → chat → reply logic (webhook and polling)."""

from __future__ import annotations

from typing import Any, Callable, Dict

from services.telegram_notify import send_telegram_message

ChatInvoke = Callable[[str, str], Dict[str, Any]]


def process_telegram_update(
    update: Dict[str, Any],
    invoke_chat: ChatInvoke,
) -> Dict[str, Any]:
    """Process one Telegram update dict; invoke_chat(message, session_id) -> {response: ...}."""
    message = update.get("message") or {}
    if "text" not in message:
        return {"ok": True, "skipped": "no text"}

    text = message["text"]
    chat_id = message.get("chat", {}).get("id", "telegram")
    session_id = f"telegram-{chat_id}"

    result = invoke_chat(text, session_id)
    ai_content = result.get("response") or ""
    sent = False
    if ai_content:
        sent = send_telegram_message(ai_content, chat_id=chat_id)

    return {
        "ok": True,
        "response": ai_content,
        "session_id": session_id,
        "telegram_sent": sent,
    }
