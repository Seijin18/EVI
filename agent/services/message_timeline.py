"""Persist ingested WhatsApp messages to contact timeline."""

from __future__ import annotations

from services.contact_filesystem import (
    append_timeline,
    ensure_contact,
    memory_enabled,
    timeline_source_ids,
)
from services.evolution_client import is_evi_bot_message
from services.message_sources import IncomingMessage


def _preview(msg: IncomingMessage) -> str:
    text = (msg.text or "").strip()
    if msg.from_me:
        return f"[eu] {text[:400]}"
    if msg.is_group:
        who = msg.label or "grupo"
        return f"[{who}] {text[:400]}"
    who = msg.label or "contato"
    return f"[{who}] {text[:400]}"


def record_whatsapp_message(msg: IncomingMessage) -> bool:
    """Append one ingested message to timeline (chat + optional participant contact)."""
    if not memory_enabled() or not msg.text.strip():
        return False
    if is_evi_bot_message(msg.text):
        return False

    chat_jid = msg.sender
    existing = timeline_source_ids(chat_jid)
    if msg.id and msg.id in existing:
        recorded = False
    else:
        recorded = append_timeline(
            chat_jid,
            source_id=msg.id or f"msg_{hash(msg.text) & 0xFFFF}",
            text_preview=_preview(msg),
            label=msg.label,
            ts=msg.ts or None,
        )

    if msg.is_group and msg.participant and "@s.whatsapp.net" in msg.participant:
        part_label = msg.label or msg.participant.split("@", 1)[0]
        ensure_contact(msg.participant, label=part_label)
        part_ids = timeline_source_ids(msg.participant)
        part_key = f"{msg.id}:p" if msg.id else f"grp_{hash(msg.text) & 0xFFFF}"
        if part_key not in part_ids:
            append_timeline(
                msg.participant,
                source_id=part_key,
                text_preview=f"[grupo] {_preview(msg)}",
                label=part_label,
                ts=msg.ts or None,
            )
            recorded = True

    return recorded


def record_whatsapp_messages(messages: list[IncomingMessage]) -> int:
    return sum(1 for m in messages if record_whatsapp_message(m))
