"""Reply debts: per-conversation WhatsApp state (evi-reply-debts).

`track_conversation` runs in the webhook before the processing filter, so it
sees `fromMe` messages that extraction later drops. It never raises and never
feeds extraction.
"""

from __future__ import annotations

import os
import re
import unicodedata
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
            from services.contact_identity import canonical_jid

            jid = canonical_jid(jid)
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
CLOSING_VERSION = 3
_CLOSING_TOKEN = (
    r"(?:ok(?:ay)?|blz|beleza|valeu|vlw|obrigad[oa]s?|brigad[oa]s?|brigadao|"
    r"de\s+nada|tmj|show|top|muito|joia|tranquilo|fechou|fechado|otimo|"
    r"perfeito|combinado|certo|entendido|"
    # v3 (SCN-PREC-01/02): short approvals, agreement and laughter
    r"boa|bom|massa|legal|bacana|dahora|demorou|falou|isso|uhum|aham|sim|"
    r"pode\s+crer|ha(?:ha)+|haha+|hehe+|k{2,}|(?:rs)+|rs+)"
)
CLOSING_RE = re.compile(
    rf"[\W_]*(?:{_CLOSING_TOKEN}(?:[\W_]+|$))+", re.IGNORECASE | re.UNICODE
)
_NO_WORDS_RE = re.compile(r"[\W_]+", re.UNICODE)

# "thanks + vocative" ("obrigado, Marcão!", "valeu Ana"): a thanks word followed
# by at most two name-like words. Anything that reads as a request/question is
# never a closing, so "valeu! me manda o contrato?" stays a debt.
_THANKS_RE = re.compile(
    r"[\W_]*(?:muito\s+)?(?:obrigad[oa]s?|brigad[oa]s?|brigadao|valeu|vlw)"
    r"(?:[\W_]+(?P<name>[^\W\d_]+(?:\s+[^\W\d_]+)?))?[\W_]*",
    re.IGNORECASE | re.UNICODE,
)
_REQUEST_RE = re.compile(
    r"\b(?:me|manda|mande|passa|passe|envia|envie|consegue|pode|poderia|qual|"
    r"quais|quando|como|onde|quem|quanto|por\s*que|preciso|queria|quero|"
    r"mas|porem|e\s+o|e\s+a)\b",
    re.IGNORECASE | re.UNICODE,
)
_NOT_A_NAME = frozenset(
    "e o a os as um uma de do da dos das pelo pela por pra para com sem "
    "que se no na em ao ja ainda tambem so la aqui".split()
)


def _fold(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn" or c == "\u20e3"
    )


def looks_like_request(text: str | None) -> bool:
    """Question or request wording ("?" or a request word); shared with awaiting_reply."""
    f = _fold((text or "").strip())
    return "?" in f or bool(_REQUEST_RE.search(f))


def is_closing_message(text: str | None) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _NO_WORDS_RE.fullmatch(t):
        return True
    f = _fold(t)
    # "pode crer" is agreement, not the request word "pode"
    if looks_like_request(re.sub(r"\bpode\s+crer\b", "", f, flags=re.IGNORECASE)):
        return False
    if CLOSING_RE.fullmatch(f):
        return True
    m = _THANKS_RE.fullmatch(f)
    if m:
        name = m.group("name") or ""
        return not any(w.lower() in _NOT_A_NAME for w in name.split())
    return False


_ACK_WINDOW = timedelta(minutes=10)
_ACK_MAX_WORDS = 3


def is_acknowledgement(preview, last_in_at, last_out_at) -> bool:
    """A short non-request reply (<= 3 words) sent within 10 min after the user's
    last message: an "aceno" ("Boa", "vou ver"), not a debt."""
    if last_out_at is None or last_in_at is None:
        return False
    try:
        delta = last_in_at - last_out_at
    except TypeError:
        return False
    if not (timedelta(0) <= delta <= _ACK_WINDOW):
        return False
    text = (preview or "").strip()
    if len(re.findall(r"[^\W_]+", text, re.UNICODE)) > _ACK_MAX_WORDS:
        return False
    return not looks_like_request(text)


def _min_hours() -> float:
    try:
        return float(os.getenv("EVI_REPLY_DEBT_HOURS", "4"))
    except ValueError:
        return 4.0


def fold_alias_states() -> None:
    """State keyed by an @lid before its alias was known folds into the phone row,
    so predicates see both sides' timestamps. Soft-fails."""
    try:
        import db
        from services.contact_identity import canonical_jid

        for st in db.list_states():
            lid = st["jid"]
            if lid.endswith("@lid") and canonical_jid(lid) != lid:
                db.merge_conversation_state(lid, canonical_jid(lid))
    except Exception as exc:  # noqa: BLE001
        soft_fail("reply_debts.fold_aliases", exc)


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
    fold_alias_states()
    rows = db.list_debt_candidates(now, timedelta(hours=hours), timedelta(days=max_days))
    # Rows keyed by an @lid that predates the migration collapse onto the phone jid.
    from services.contact_identity import canonical_jid

    latest: dict[str, dict] = {}
    for r in rows:
        cj = canonical_jid(r["jid"])
        if cj not in latest or r["last_in_at"] > latest[cj]["last_in_at"]:
            latest[cj] = {**r, "jid": cj}
    rows = sorted(latest.values(), key=lambda r: r["last_in_at"])
    out: list[dict] = []
    for r in rows:
        preview = r.get("last_in_preview") or ""
        if is_one_way_jid(r["jid"]) or is_closing_message(preview):
            continue
        if is_acknowledgement(preview, r["last_in_at"], r.get("last_out_at")):
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
