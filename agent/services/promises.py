"""Promise capture from the user's own WhatsApp messages (evi-reply-debts, §2).

Deterministic pt-BR heuristic, no LLM. Runs in the webhook right after
`reply_debts.track_conversation` (fromMe never reaches extraction). Only the
user's own words are stored; the briefing wraps them when rendering.
"""

from __future__ import annotations

import os
import re
import unicodedata
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

# Bare acknowledgements ("pode deixar", "aí eu te aviso") carry no object: nothing
# to track. A promise needs at least one word left after removing these.
_FILLER = frozenset(
    "a ai ahh ahn ah ok okk okay blz ss sim eu e ja ta to q que pra pro de da do no na um uma "
    "pera calma ele ela quando assim aqui la ent entao tb tbm tambem "
    "pode deixar deixa comigo te mando envio passo aviso falo".split()
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _has_substance(norm: str) -> bool:
    return any(w not in _FILLER for w in _WORD_RE.findall(norm))


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
            return _has_substance(norm)
    return False


def _short_title(text: str, limit: int = 80) -> str:
    one_line = " ".join((text or "").split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1].rstrip() + "…"


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
                status="pending",
            )
            if row_id:
                stored += 1
        except Exception as exc:  # noqa: BLE001
            soft_fail("promises.capture_message", exc)
    return stored
