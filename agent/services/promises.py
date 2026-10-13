"""Promise capture from the user's own WhatsApp messages (evi-reply-debts, §2).

Deterministic pt-BR heuristic, no LLM. Runs in the webhook right after
`reply_debts.track_conversation` (fromMe never reaches extraction). Only the
user's own words are stored; the briefing wraps them when rendering.
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Iterable

from services.soft_fail import soft_fail

# Versioned: bump when the vocabulary changes. Matched against lowercase,
# accent-stripped text.
PROMISE_PATTERNS_VERSION = 1
PROMISE_PATTERNS = (
    r"\bte\s+mando\b",
    r"\bte\s+envio\b",
    r"\bte\s+passo\b",
    r"\bte\s+aviso\b",
    r"\bte\s+falo\b",
    r"\bte\s+respondo\b",
    r"\bte\s+retorno\b",
    r"\bamanha\s+te\b",
    r"\bdepois\s+te\b",
    r"\bvou\s+ver\s+e\b",
    r"\bdeixa\s+comigo\b",
    r"\bpode\s+deixar\b",
)
_PROMISE_RE = re.compile("|".join(PROMISE_PATTERNS))
_NEGATION_RE = re.compile(r"\b(?:nao|nunca|jamais)\s+(?:\w+\s+){0,2}$")
_SOURCE = "whatsapp_from_me"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def detect_promise(text: str) -> bool:
    """True when `text` reads as the user promising something to the other person."""
    norm = _normalize(text).strip()
    if not norm or norm.endswith("?"):
        return False
    for m in _PROMISE_RE.finditer(norm):
        if not _NEGATION_RE.search(norm[: m.start()]):
            return True
    return False


def _short_title(text: str, limit: int = 80) -> str:
    one_line = " ".join((text or "").split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1].rstrip() + "…"


def promise_context_enabled() -> bool:
    """EVI_PROMISE_CONTEXT_ENABLED; unset follows EVI_REPLY_DEBTS_ENABLED."""
    raw = os.getenv("EVI_PROMISE_CONTEXT_ENABLED", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    from services.whatsapp_processor import reply_debts_enabled

    return reply_debts_enabled()


def _eval_delay_min() -> int:
    try:
        return max(0, int(os.getenv("EVI_PROMISE_EVAL_DELAY_MIN", "30")))
    except ValueError:
        return 30


def _msg_dt(ts: str) -> datetime:
    """Message timestamp as an aware UTC datetime (now() when unparseable)."""
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


def capture_promises(messages: Iterable) -> int:
    """Store a pending 'promise' per direct fromMe message that matches.

    Returns the number of promises stored. Idempotent via unique (source, source_id).
    Soft-fails every error; no-op without DATABASE_URL.
    """
    if not os.getenv("DATABASE_URL"):
        return 0
    try:
        import db
        from services.contact_registry import effective_label
        from services.evolution_client import is_evi_bot_message
        from services.whatsapp_control import parse_control_jids
        from services.whatsapp_processor import _parse_ref_dt, _resolve_date, _resolve_time

        control = parse_control_jids()
    except Exception as exc:  # noqa: BLE001
        soft_fail("promises.setup", exc)
        return 0

    stored = 0
    for msg in messages:
        try:
            jid = msg.sender
            if not msg.from_me or msg.is_group or "@g.us" in jid or jid in control:
                continue
            if is_evi_bot_message(msg.text) or not detect_promise(msg.text):
                continue
            try:
                ref = _parse_ref_dt(msg.ts)
            except Exception:  # noqa: BLE001
                from datetime import datetime

                ref = datetime.now()
            label = ""
            try:
                label = effective_label(db.get_whatsapp_contact(jid), fallback="")
            except Exception as exc:  # noqa: BLE001
                soft_fail("promises.label", exc)
            ctx_on = promise_context_enabled()
            extra: dict = {}
            if ctx_on:
                msg_dt = _msg_dt(msg.ts)
                extra = {
                    "next_eval_at": msg_dt + timedelta(minutes=_eval_delay_min()),
                    "msg_ts": msg_dt,
                }
            row_id = db.insert_pending_commitment(
                source=_SOURCE,
                source_id=msg.id,
                ctype="promise",
                title=_short_title(msg.text),
                event_time=_resolve_time(msg.text),
                due_date=_resolve_date(msg.text, ref),
                raw_text=msg.text,
                source_chat=jid,
                source_label=label,
                status="needs_eval" if ctx_on else "pending",
                **extra,
            )
            if row_id:
                stored += 1
        except Exception as exc:  # noqa: BLE001
            soft_fail("promises.capture_message", exc)
    return stored
