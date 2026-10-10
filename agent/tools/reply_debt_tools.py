"""Tools to list and dismiss WhatsApp reply debts (evi-reply-debts).

Both work regardless of EVI_REPLY_DEBTS_ENABLED: listing is read-only and
dismissing only writes an acknowledgement, so neither is gated by the flag.
"""

from __future__ import annotations

from langchain_core.tools import tool


def _fmt_age(hours: float) -> str:
    if hours < 48:
        return f"{max(1, int(hours))} h"
    return f"{int(hours // 24)} d"


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
def dismiss_reply_debt(jid_or_name: str) -> str:
    """Mark a conversation as answered/ignored so it stops appearing as a reply debt
    (until a new inbound message arrives). Use for «respondido», «ignora <contato>».
    jid_or_name: contact name, alias, last phone digits or full JID.
    """
    from services.contact_filesystem import resolve_contact_for_query
    from tools.calendar_time import now_local

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
