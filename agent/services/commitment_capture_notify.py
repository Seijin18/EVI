"""Notify WhatsApp control JIDs when a commitment is captured from a group message."""

from __future__ import annotations

import logging
import os

from services.evolution_client import send_whatsapp_text

logger = logging.getLogger(__name__)

_CTYPE_LABEL = {"event": "evento", "task": "tarefa"}


def _control_jids() -> list[str]:
    raw = os.getenv("EVI_WHATSAPP_CONTROL_JIDS", "").strip()
    if not raw:
        return []
    return [j.strip() for j in raw.split(",") if j.strip()]


def notify_commitment_captured(
    commitment_id: int,
    title: str,
    ctype: str,
) -> None:
    """Send a short capture-confirmation to every configured control JID.

    Silently no-ops when control JIDs are not configured or send fails.
    """
    from services.whatsapp_processor import reply_debts_enabled

    if reply_debts_enabled():
        logger.info("capture notification skipped (reply debts on): #%s", commitment_id)
        return
    jids = _control_jids()
    if not jids:
        return

    label = _CTYPE_LABEL.get(ctype, ctype)
    text = f"Capturado #{commitment_id}: {title[:80]} ({label})"

    for jid in jids:
        try:
            send_whatsapp_text(jid, text, add_prefix=True)
        except Exception as exc:
            from services.soft_fail import soft_fail
            soft_fail("commitment_capture_notify.notify_commitment_captured", exc)
