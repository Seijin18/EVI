"""People who have not answered the user (evi-awaiting-their-reply).

The mirror of reply debts: the user spoke last, with a question or request, a few days
ago. Deterministic (no LLM), read-only toward the contact: this module never sends
anything. Dismissals are per outbound message (`awaiting_dismissed(jid, out_at)`), so a
newer message from the user reopens the conversation.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from services.reply_debts import (
    _contact_name,
    _fold,
    fold_alias_states,
    is_closing_message,
    is_one_way_jid,
    looks_like_request,
)
from services.soft_fail import soft_fail

MAX_DAYS = 30
EXCERPT_MAX = 80
_EU = "[eu] "
_TIMELINE_TAIL = 40
_TS_SLACK = timedelta(minutes=10)
# Request wording that the debt heuristic does not cover (it targets what others ask the user).
_EXTRA_REQUEST_RE = re.compile(r"\b(?:tem\s+como|voce\s+vai|vc\s+vai|me\s+confirma|confirma)\b", re.IGNORECASE)


def enabled() -> bool:
    return os.getenv("EVI_AWAITING_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")


def min_days() -> float:
    try:
        return float(os.getenv("EVI_AWAITING_DAYS", "3"))
    except ValueError:
        return 3.0


def is_request(text: str | None) -> bool:
    return looks_like_request(text) or bool(_EXTRA_REQUEST_RE.search(_fold(text or "")))


def _parse_ts(raw) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def last_user_text(jid: str, out_at: datetime) -> str:
    """The user's last message text from the contact timeline ("" when unknown).

    An ``[eu]`` entry far older than ``out_at`` is not the message that set ``last_out_at``
    (it predates two-sided timelines): treated as unknown.
    """
    from services import contact_filesystem as cf

    for entry in reversed(cf.read_timeline_tail(jid, limit=_TIMELINE_TAIL)):
        preview = str(entry.get("text_preview") or "")
        if not preview.startswith(_EU):
            continue
        ts = _parse_ts(entry.get("ts"))
        if ts is not None and ts < out_at - _TS_SLACK:
            return ""
        return preview[len(_EU):].strip()
    return ""


def excerpt(text: str) -> str:
    from services.untrusted import plain_external

    return plain_external(text, EXCERPT_MAX)


def candidates(now: datetime | None = None, limit: int = 3) -> list[dict]:
    """Direct conversations awaiting the other side, oldest first:
    ``[{jid, label, out_at, days, excerpt}]``."""
    import db
    from services.contact_identity import canonical_jid
    from services.whatsapp_control import parse_control_jids

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    db.init_db()
    fold_alias_states()
    control = parse_control_jids()
    from services.contact_registry import effective_label

    rows = db.list_awaiting_candidates(now, timedelta(days=min_days()), timedelta(days=MAX_DAYS))
    latest: dict[str, dict] = {}
    for r in rows:  # rows keyed by an unmerged @lid collapse onto the phone jid
        cj = canonical_jid(r["jid"])
        if cj not in latest or r["last_out_at"] > latest[cj]["last_out_at"]:
            latest[cj] = {**r, "jid": cj}
    out: list[dict] = []
    for r in sorted(latest.values(), key=lambda r: r["last_out_at"]):
        jid, out_at = r["jid"], r["last_out_at"]
        if "@g.us" in jid or jid in control or is_one_way_jid(jid):
            continue
        try:
            text = last_user_text(jid, out_at)
            if not text or is_closing_message(text) or not is_request(text):
                continue
            if db.is_awaiting_dismissed(jid, out_at):
                continue
            out.append(
                {
                    "jid": jid,
                    "label": _contact_name(jid, effective_label),
                    "out_at": out_at,
                    "days": int((now - out_at).total_seconds() // 86400),
                    "excerpt": excerpt(text),
                }
            )
        except Exception as exc:  # noqa: BLE001
            soft_fail("awaiting_reply.candidate", exc)
            continue
        if len(out) >= limit:
            break
    return out


def dismiss(jid: str, out_at: datetime) -> None:
    """Stop listing this exact outbound message (idempotent)."""
    import db

    db.init_db()
    db.dismiss_awaiting(jid, out_at)
