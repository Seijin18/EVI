"""Tools to list and dismiss WhatsApp reply debts (evi-reply-debts).

Both work regardless of EVI_REPLY_DEBTS_ENABLED: listing is read-only and
dismissing only writes an acknowledgement, so neither is gated by the flag.
"""

from __future__ import annotations

from langchain_core.tools import tool
from services.write_guard import guarded_write


def _fmt_age(hours: float) -> str:
    if hours < 48:
        return f"{max(1, int(hours))} h"
    return f"{int(hours // 24)} d"


def _debt_names(jids: list[str]) -> list[str]:
    """Nomes legíveis (nunca JID cru) das conversas, na ordem de ``jids``."""
    from services.reply_debts import list_debts
    from services.untrusted import plain_external
    from services.ux_format import who_label

    try:
        by_jid = {d["jid"]: d.get("name") or "" for d in list_debts()}
    except Exception:  # noqa: BLE001 - the ack must not fail because the name lookup did
        by_jid = {}
    return [plain_external(who_label(by_jid.get(j) or j), 40) for j in jids]


def _ack_text(names: list[str], n: int) -> str:
    """Confirmação com o NOME da pessoa (até 3); acima disso, a contagem."""
    if n == 1:
        return f"Ok, {names[0]} não aparece mais como pendente de resposta."
    if n <= 3:
        listed = ", ".join(names[:-1]) + f" e {names[-1]}"
        return f"Ok, {listed} não aparecem mais como pendentes de resposta."
    return f"Ok, {n} conversas não aparecem mais como pendentes de resposta."


@tool
def list_reply_debts() -> str:
    """List WhatsApp conversations where someone is waiting for the user's reply.
    Use for «quem está esperando resposta?», «o que eu não respondi?».
    """
    from services.reply_debts import list_debts
    from services.untrusted import wrap_external

    debts = list_debts()
    if not debts:
        return "Ninguém esperando sua resposta."
    lines = [
        f"{d['name']} — há {_fmt_age(d['age_h'])}: {wrap_external(d['preview'], source='whatsapp')}"
        for d in debts
    ]
    return "\n".join(lines)


@tool
@guarded_write
def dismiss_reply_debt(jid_or_name: str = "", briefing_items: list[int] | None = None) -> str:
    """Mark a conversation as answered/ignored so it stops appearing as a reply debt
    (until a new inbound message arrives). Use for «respondido», «ignora <contato>».
    jid_or_name: contact name, alias, last phone digits or full JID.
    If the user refers to numbers from the last briefing ('respondido 1', 'ignora 2'),
    pass them in briefing_items — never in jid_or_name. Otherwise leave briefing_items
    empty and use jid_or_name. Never guess numbers.
    """
    from services.contact_filesystem import resolve_contact_for_query
    from tools.calendar_time import now_local

    if briefing_items:
        from services.briefing import resolve_briefing_items

        jids, errors = resolve_briefing_items(list(briefing_items), kind="reply_debt")
        names = _debt_names(jids) if jids else []
        if jids:
            import db

            db.init_db()
            now = now_local()
            for jid in jids:
                db.acknowledge(jid, now)
        parts = [_ack_text(names, len(jids))] if jids else []
        return "\n".join(parts + errors)
    q = (jid_or_name or "").strip()
    if not q:
        return "Informe o contato (nome, telefone ou JID)."
    if "@" in q:
        jid, label = q, q.split("@", 1)[0]
    else:
        resolved, err = resolve_contact_for_query(q)
        if not resolved:
            return err
        jid, label = resolved

    import db

    db.init_db()
    db.acknowledge(jid, now_local())
    return f"Ok, {label} não aparece mais como pendente de resposta."
