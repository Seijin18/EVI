"""Notify WhatsApp control JIDs when a commitment is captured from a group message."""

from __future__ import annotations

import os

from services.evolution_client import send_whatsapp_text

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
    jids = _control_jids()
    if not jids:
        return

    label = _CTYPE_LABEL.get(ctype, ctype)
    text = f"Capturado #{commitment_id}: {title[:80]} ({label})"

    for jid in jids:
        try:
            send_whatsapp_text(jid, text, add_prefix=True)
        except Exception:
            pass
