"""Reply debts: per-conversation WhatsApp state (evi-reply-debts).

`track_conversation` runs in the webhook before the processing filter, so it
sees `fromMe` messages that extraction later drops. It never raises and never
feeds extraction.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable

from services.soft_fail import soft_fail


def _parse_ts(ts: str) -> datetime:
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def track_conversation(messages: Iterable) -> int:
    """Record inbound/outbound state for direct, non-control, non-echo messages.

    Returns the number of messages recorded. Soft-fails every error.
    """
    if not os.getenv("DATABASE_URL"):
        return 0
    try:
        import db
        from services.evolution_client import is_evi_bot_message
        from services.whatsapp_control import parse_control_jids

        db.init_db()
        control = parse_control_jids()
    except Exception as exc:  # noqa: BLE001
        soft_fail("reply_debts.track_setup", exc)
        return 0

    recorded = 0
    for msg in messages:
        try:
            jid = msg.sender
            if msg.is_group or "@g.us" in jid or jid in control:
                continue
            if is_evi_bot_message(msg.text):
                continue
            ts = _parse_ts(msg.ts)
            if msg.from_me:
                db.record_outbound(jid, ts)
            else:
                db.record_inbound(jid, ts, msg.text, msg.id)
            recorded += 1
        except Exception as exc:  # noqa: BLE001
            soft_fail("reply_debts.track_message", exc)
    return recorded
