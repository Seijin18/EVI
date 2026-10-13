"""Learn per-contact knowledge (facts / open items) from the stored conversation."""

from __future__ import annotations

from services.contact_filesystem import resolve_contact_for_query
from services.contact_knowledge import read_contact_knowledge, update_contact_knowledge
from services.untrusted import wrap_external
from services.whatsapp_backfill import backfill_contact_full


def learn_contact(
    name_or_phone: str,
    days: int = 30,
    *,
    fetch_messages: bool = True,
) -> str:
    """Backfill WhatsApp history (optional) then update the contact's structured knowledge.

    ``days`` bounds the backfill only; the knowledge update reads the timeline messages
    newer than the profile's last update (see ``update_contact_knowledge``; the first run
    uses the last 30 days stored).
    """
    days = max(1, min(int(days), 90))
    resolved, err = resolve_contact_for_query(name_or_phone)
    if not resolved:
        return err
    jid, label = resolved

    backfill_note = ""
    if fetch_messages:
        br = backfill_contact_full(jid, label=label, days=days)
        backfill_note = br.summary(label, days)
        if br.error and br.fetched == 0:
            backfill_note += "\n\n"
        from services.commitment_replay import replay_commitments_from_evolution_log

        replay = replay_commitments_from_evolution_log(jid=jid, days=days)
        if replay.queued:
            backfill_note += f"\n{replay.summary()}\n"

    try:
        result = update_contact_knowledge(jid)
    except Exception as exc:
        return f"Não consegui atualizar agora: {str(exc)[:180]}"

    status = result.get("status")
    if status == "no-messages":
        hint = f"Não há mensagens novas sobre «{label}» desde a última atualização."
        if fetch_messages:
            hint += (
                " A Evolution pode não ter histórico antigo em cache; "
                "tente conversar com o contato ou habilitar syncFullHistory na instância."
            )
        return f"{backfill_note}\n{hint}" if backfill_note else hint
    if status != "ok":
        return f"Não consegui atualizar agora: {status}."

    body = (
        f"Conhecimento sobre **{wrap_external(label, 'perfil_contato', 120)}** atualizado: "
        f"+{result['added']} fato(s), -{result['removed']} removido(s), "
        f"{result['open']} em aberto (aprende só as mensagens novas desde a última atualização).\n\n"
        f"{wrap_external(read_contact_knowledge(jid), 'perfil_contato', 4000)}"
    )
    if backfill_note:
        body = f"{backfill_note}\n\n{body}"
    return body
