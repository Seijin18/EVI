"""Shared Telegram update → chat → reply logic (webhook and polling)."""

from __future__ import annotations

from typing import Any, Callable, Dict

from llm import extract_llm_text
from services.direct_handlers import direct_handlers_enabled
from services.telegram_audit import log_telegram_turn
from services.telegram_format import format_for_telegram
from services.commitment_review.handler import try_direct_review
from services.telegram_notify import send_telegram_message
from services.direct_email import try_direct_email
from services.direct_task import try_direct_task
from services.telegram_schedule import try_direct_schedule

ChatInvoke = Callable[[str, str], Dict[str, Any]]


def _persist_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    try:
        from db import init_db, save_message

        init_db()
        save_message(session_id, "user", user_text)
        save_message(session_id, "assistant", assistant_text)
    except Exception:
        pass


def _reply_direct(
    *,
    session_id: str,
    chat_id: Any,
    text: str,
    ai_content: str,
    tools: list,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ai_content = format_for_telegram(extract_llm_text(ai_content))
    sent = send_telegram_message(ai_content, chat_id=chat_id) if ai_content else False
    _persist_turn(session_id, text, ai_content)
    log_telegram_turn(
        session_id,
        text,
        ai_content,
        tools,
        telegram_sent=sent,
    )
    out: Dict[str, Any] = {
        "ok": True,
        "response": ai_content,
        "session_id": session_id,
        "telegram_sent": sent,
    }
    if extra:
        out.update(extra)
    return out


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

    if direct_handlers_enabled():
        reviewed = try_direct_review(text, confirmed_via="telegram")
        if reviewed:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=reviewed,
                tools=[{"type": "direct", "tool": "commitment_review"}],
                extra={"review_direct": True},
            )

        direct = try_direct_schedule(text)
        if direct:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=direct,
                tools=[{"type": "direct", "tool": "schedule_event"}],
                extra={"scheduled_direct": True},
            )

        tasked = try_direct_task(text)
        if tasked:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=tasked,
                tools=[{"type": "direct", "tool": "create_task"}],
                extra={"task_direct": True},
            )

        emailed = try_direct_email(text)
        if emailed:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=emailed,
                tools=[{"type": "direct", "tool": "summarize_inbox"}],
                extra={"email_direct": True},
            )

    try:
        result = invoke_chat(text, session_id)
    except Exception as exc:
        detail = str(exc)
        ai_content = (
            "Não consegui processar sua mensagem agora. "
            f"Detalhe: {detail[:180]}"
        )
        return _reply_direct(
            session_id=session_id,
            chat_id=chat_id,
            text=text,
            ai_content=ai_content,
            tools=[{"type": "error", "detail": detail[:500]}],
            extra={"error": True},
        )

    try:
        from services.profile_updater import extract_profile_facts, merge_profile

        merge_profile(str(chat_id), extract_profile_facts(text))
    except Exception:
        pass

    tools = result.get("tools") or []
    output_messages = result.get("output_messages") or []
    audit_payload = tools if tools else output_messages
    return _reply_direct(
        session_id=session_id,
        chat_id=chat_id,
        text=text,
        ai_content=result.get("response") or "",
        tools=audit_payload if isinstance(audit_payload, list) else [],
        extra={"llm": True},
    )
