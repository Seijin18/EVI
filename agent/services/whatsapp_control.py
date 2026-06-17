"""WhatsApp control JID: chat with EVI and run review commands."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Set

from llm import extract_llm_text
from services.commitment_review.handler import try_direct_review
from services.direct_email import try_direct_email
from services.direct_handlers import direct_handlers_enabled
from services.direct_task import try_direct_task
from services.evolution_client import (
    format_evi_whatsapp,
    is_evi_bot_message,
    send_whatsapp_text,
)
from services.telegram_schedule import try_direct_schedule


def parse_control_jids() -> Set[str]:
    raw = os.getenv("EVI_WHATSAPP_CONTROL_JIDS", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


ChatInvoke = Callable[[str, str], Dict[str, Any]]


def process_whatsapp_control_message(
    *,
    jid: str,
    text: str,
    invoke_chat: ChatInvoke,
) -> Dict[str, Any]:
    """Handle a user message from a control JID; reply via Evolution."""
    session_id = f"whatsapp-{jid}"

    if is_evi_bot_message(text):
        return {"ok": True, "skipped": "evi_echo"}

    if direct_handlers_enabled():
        direct = try_direct_review(text, confirmed_via="whatsapp")
        if direct:
            reply = direct
            sent = send_whatsapp_text(jid, reply, add_prefix=True)
            return {
                "ok": True,
                "response": format_evi_whatsapp(reply),
                "session_id": session_id,
                "whatsapp_sent": sent,
                "review_direct": True,
            }

        scheduled = try_direct_schedule(text)
        if scheduled:
            sent = send_whatsapp_text(jid, scheduled, add_prefix=True)
            return {
                "ok": True,
                "response": format_evi_whatsapp(scheduled),
                "session_id": session_id,
                "whatsapp_sent": sent,
                "scheduled_direct": True,
            }

        tasked = try_direct_task(text)
        if tasked:
            sent = send_whatsapp_text(jid, tasked, add_prefix=True)
            return {
                "ok": True,
                "response": format_evi_whatsapp(tasked),
                "session_id": session_id,
                "whatsapp_sent": sent,
                "task_direct": True,
            }

        emailed = try_direct_email(text)
        if emailed:
            sent = send_whatsapp_text(jid, emailed, add_prefix=True)
            return {
                "ok": True,
                "response": format_evi_whatsapp(emailed),
                "session_id": session_id,
                "whatsapp_sent": sent,
                "email_direct": True,
            }

    try:
        result = invoke_chat(text, session_id)
        reply = extract_llm_text(result.get("response"))
    except Exception as exc:
        reply = f"Não consegui processar agora. Detalhe: {str(exc)[:180]}"
        result = {}

    if not reply:
        reply = (
            "Não obtive resposta do agente. Descreva o que precisa "
            "(emails, compromissos, tarefas ou calendário)."
        )

    try:
        from services.profile_updater import extract_profile_facts, merge_profile

        merge_profile(jid, extract_profile_facts(text))
    except Exception:
        pass

    sent = send_whatsapp_text(jid, reply, add_prefix=True)
    return {
        "ok": True,
        "response": format_evi_whatsapp(reply) if reply else "",
        "session_id": session_id,
        "whatsapp_sent": sent,
        "llm": True,
        "tools": result.get("tools") or [],
    }
