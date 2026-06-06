"""Deliver commitment notifications to configured channels."""

from __future__ import annotations

import os
from typing import Iterable, List

from db import count_unnotified_pending, list_pending_commitments, mark_pending_notified
from services.commitment_review.digest import format_pending_digest
from services.commitment_review.channels.telegram import send_telegram_message
from services.commitment_review.channels.whatsapp import send_whatsapp_text

_HIGH = frozenset({"urgent", "work", "university"})


def _notify_channels() -> List[str]:
    raw = os.getenv("EVI_NOTIFY_CHANNELS", "telegram").strip().lower()
    return [c.strip() for c in raw.split(",") if c.strip()]


def _control_jids() -> List[str]:
    raw = os.getenv("EVI_WHATSAPP_CONTROL_JIDS", "").strip()
    return [j.strip() for j in raw.split(",") if j.strip()]


def _send_whatsapp_digest(text: str) -> bool:
    sent = False
    for jid in _control_jids():
        if send_whatsapp_text(jid, text, add_prefix=True):
            sent = True
    return sent


def maybe_notify_new_pending(
    queued_ids: List[int],
    priorities: Iterable[str],
) -> bool:
    if not queued_ids:
        return False
    high = any(p in _HIGH for p in priorities)
    unnotified = count_unnotified_pending()
    if not high and unnotified < 5:
        return False
    rows = [r for r in list_pending_commitments(limit=10) if not r.get("notified_at")]
    if not rows:
        return False
    text = format_pending_digest(rows)
    sent_any = False
    for ch in _notify_channels():
        if ch == "telegram" and send_telegram_message(text):
            sent_any = True
        elif ch == "whatsapp" and _send_whatsapp_digest(text):
            sent_any = True
    if sent_any:
        mark_pending_notified([r["id"] for r in rows])
        return True
    return False
