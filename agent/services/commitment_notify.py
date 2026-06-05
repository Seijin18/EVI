"""Notify user about new pending commitments (Telegram)."""

from __future__ import annotations

from typing import Iterable, List

from db import count_unnotified_pending, list_pending_commitments, mark_pending_notified
from services.telegram_notify import format_pending_digest, send_telegram_message

_HIGH = frozenset({"urgent", "work", "university"})


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
    if send_telegram_message(text):
        mark_pending_notified([r["id"] for r in rows])
        return True
    return False
