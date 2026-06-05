"""Shared Telegram update → chat → reply logic (webhook and polling)."""

from __future__ import annotations

from typing import Any, Callable, Dict

from services.telegram_audit import log_telegram_turn
from services.telegram_format import format_for_telegram
from services.telegram_notify import send_telegram_message
from services.telegram_schedule import try_direct_schedule

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

    direct = try_direct_schedule(text)
    if direct:
        ai_content = format_for_telegram(direct)
        sent = send_telegram_message(ai_content, chat_id=chat_id) if ai_content else False
        try:
            from db import init_db, save_message

            init_db()
            save_message(session_id, "user", text)
            save_message(session_id, "assistant", ai_content)
        except Exception:
            pass
        log_telegram_turn(
            session_id,
            text,
            ai_content,
            [{"type": "direct", "tool": "schedule_event"}],
            telegram_sent=sent,
        )
        return {
            "ok": True,
            "response": ai_content,
            "session_id": session_id,
            "telegram_sent": sent,
            "scheduled_direct": True,
        }

    result = invoke_chat(text, session_id)
    ai_content = format_for_telegram(result.get("response") or "")
    sent = False
    if ai_content:
        sent = send_telegram_message(ai_content, chat_id=chat_id)

    return {
        "ok": True,
        "response": ai_content,
        "session_id": session_id,
        "telegram_sent": sent,
    }
