"""WhatsApp control JID: chat with EVI and run review commands."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Set

from services.commitment_review.handler import try_direct_review
from services.evolution_client import (
    format_evi_whatsapp,
    is_evi_bot_message,
    send_whatsapp_text,
)


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

    try:
        result = invoke_chat(text, session_id)
        reply = result.get("response") or ""
    except Exception as exc:
        reply = f"Não consegui processar agora. Detalhe: {str(exc)[:180]}"

    sent = send_whatsapp_text(jid, reply, add_prefix=True) if reply else False
    return {
        "ok": True,
        "response": format_evi_whatsapp(reply) if reply else "",
        "session_id": session_id,
        "whatsapp_sent": sent,
    }
