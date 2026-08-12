"""Production heartbeat — checklist + notify control JIDs."""

from __future__ import annotations

from typing import Any

from services.daily_summary import heartbeat_enabled, run_heartbeat_dry
from services.whatsapp_control import parse_control_jids


def run_heartbeat(*, dry: bool = False) -> dict[str, Any]:
    """Execute heartbeat checklist; notify control chat when enabled."""
    if dry or not heartbeat_enabled():
        return run_heartbeat_dry()

    out = run_heartbeat_dry()
    messages: list[str] = []

    pending = int(out.get("pending_unnotified") or 0)
    if pending > 0:
        messages.append(
            f"{pending} compromisso(s) WhatsApp pendente(s) não notificado(s). "
            "Diga «listar pendentes» para revisar."
        )

    stale = _contacts_needing_synthesis()
    if stale:
        names = ", ".join(stale[:3])
        extra = f" (+{len(stale) - 3})" if len(stale) > 3 else ""
        messages.append(
            f"Contatos com timeline recente sem síntese: {names}{extra}. "
            "Peça «aprenda sobre <nome> nos últimos 7 dias»."
        )

    checklist = (out.get("checklist") or "").strip()
    if checklist and not messages:
        messages.append("Heartbeat OK — nada urgente no checklist.")

    notified = 0
    jids = parse_control_jids()
    if messages and jids:
        from services.evolution_client import send_whatsapp_text

        body = "\n".join(f"• {m}" for m in messages)
        for jid in jids:
            if send_whatsapp_text(jid, body, add_prefix=True):
                notified += 1

    out["messages"] = messages
    out["notified_jids"] = notified
    out["ran"] = True
    return out


def _contacts_needing_synthesis(*, days: int = 7) -> list[str]:
    try:
        from services.contact_filesystem import (
            collect_known_contacts,
            last_synthesis_date,
            memory_enabled,
            read_timeline_since,
        )

        if not memory_enabled():
            return []
        stale: list[str] = []
        for c in collect_known_contacts():
            jid = c.get("jid") or ""
            label = c.get("label") or jid
            recent = read_timeline_since(jid, days=days)
            if not recent:
                continue
            last_ts = (recent[-1].get("ts") or "")[:10]
            if not last_ts:
                continue
            # Both sides are ISO dates, so lexicographic order is chronological.
            # A missing or unparseable heading yields "", and last_ts > "" flags
            # it: a false "needs synthesis" is noise, a false "already done"
            # hides real work.
            if last_ts > last_synthesis_date(jid):
                stale.append(label)
        return stale
    except Exception as exc:
        from services.soft_fail import soft_fail

        soft_fail("heartbeat._contacts_needing_synthesis", exc)
        return []
