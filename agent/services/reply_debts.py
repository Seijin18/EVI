"""Reply debts: per-conversation WhatsApp state (evi-reply-debts).

`track_conversation` runs in the webhook before the processing filter, so it
sees `fromMe` messages that extraction later drops. It never raises and never
feeds extraction.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
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


# WhatsApp Channels / status broadcasts: one-way, there is nobody to answer.
_ONE_WAY_SUFFIXES = ("@newsletter", "@broadcast")


def is_one_way_jid(jid: str) -> bool:
    return (jid or "").endswith(_ONE_WAY_SUFFIXES)


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
            if msg.is_group or "@g.us" in jid or jid in control or is_one_way_jid(jid):
                continue
            if is_evi_bot_message(msg.text):
                continue
            ts = _parse_ts(msg.ts)
            if msg.from_me:
                db.record_outbound(jid, ts)
                # fromMe never reaches extraction; it still belongs in the timeline.
                from services.message_timeline import record_whatsapp_message

                record_whatsapp_message(msg)
            else:
                preview = "[áudio]" if getattr(msg, "kind", "text") == "audio" else msg.text
                db.record_inbound(jid, ts, preview, msg.id)
            recorded += 1
        except Exception as exc:  # noqa: BLE001
            soft_fail("reply_debts.track_message", exc)
    return recorded


# --- debt query (SCN-DEBT-01, SCN-DEBT-03) -----------------------------------

# Versioned: bump when the vocabulary changes. A message is "closing" only when
# EVERY word is one of these (or it has no words at all: emoji/punctuation only),
# so "ok, me manda amanhã?" still counts as a debt.
CLOSING_VERSION = 1
_CLOSING_TOKEN = (
    r"(?:ok(?:ay)?|blz|beleza|valeu|vlw|obrigad[oa]s?|brigad[oa]s?|"
    r"de\s+nada|tmj|show|top|muito)"
)
CLOSING_RE = re.compile(
    rf"[\W_]*(?:{_CLOSING_TOKEN}(?:[\W_]+|$))+", re.IGNORECASE | re.UNICODE
)
_NO_WORDS_RE = re.compile(r"[\W_]+", re.UNICODE)


def is_closing_message(text: str | None) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_NO_WORDS_RE.fullmatch(t) or CLOSING_RE.fullmatch(t))


def _min_hours() -> float:
    try:
        return float(os.getenv("EVI_REPLY_DEBT_HOURS", "4"))
    except ValueError:
        return 4.0


def list_debts(
    now: datetime | None = None,
    min_hours: float | None = None,
    max_days: float = 7,
    limit: int = 20,
) -> list[dict]:
    """Unanswered direct conversations, oldest first: [{jid, name, since, age_h, preview}]."""
    import db
    from services.contact_registry import effective_label

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    hours = _min_hours() if min_hours is None else min_hours
    db.init_db()
    rows = db.list_debt_candidates(now, timedelta(hours=hours), timedelta(days=max_days))
    out: list[dict] = []
    for r in rows:
        preview = r.get("last_in_preview") or ""
        if is_one_way_jid(r["jid"]) or is_closing_message(preview):
            continue
        since = r["last_in_at"]
        out.append(
            {
                "jid": r["jid"],
                "name": _contact_name(r["jid"], effective_label),
                "since": since,
                "age_h": (now - since).total_seconds() / 3600,
                "preview": preview,
            }
        )
        if len(out) >= limit:
            break
    return out


def _contact_name(jid: str, effective_label) -> str:
    fallback = jid.split("@", 1)[0]
    try:
        import db

        return effective_label(db.get_whatsapp_contact(jid), fallback=fallback)
    except Exception as exc:  # noqa: BLE001
        soft_fail("reply_debts.contact_name", exc)
        return fallback
