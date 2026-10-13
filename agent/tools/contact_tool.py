"""WhatsApp contact lookup by name or phone — no JID required from the user."""

from __future__ import annotations

from langchain_core.tools import tool
from services.write_guard import guarded_write

from services.contact_filesystem import (
    collect_known_contacts,
    ensure_contact,
    is_direct_jid,
    memory_enabled,
    read_timeline_tail,
    resolve_contact_for_query,
    search_contacts,
)
from services.contact_knowledge import read_contact_knowledge
from services.contact_learning import learn_contact
from services.untrusted import wrap_external
from services.contact_registry import assign_contact_name, format_contact_names, sync_evolution_contacts
from services.whatsapp_activity import list_recent_whatsapp, summarize_whatsapp
from services.whatsapp_backfill import backfill_contact_full


def _format_phone_hint(jid: str) -> str:
    digits = "".join(c for c in jid.split("@", 1)[0] if c.isdigit())
    if len(digits) >= 12 and digits.startswith("55"):
        ddd = digits[2:4]
        rest = digits[4:]
        if len(rest) >= 8:
            return f"+55 {ddd} {rest[:5]}-{rest[5:9]}"
    return ""


def _format_contact_block(contact: dict) -> list[str]:
    jid = contact["jid"]
    label = contact.get("label") or jid
    try:
        from db import get_whatsapp_contact, init_db

        init_db()
        db_row = get_whatsapp_contact(jid)
    except Exception:
        db_row = None
    title = format_contact_names(db_row or contact, label)
    lines = [f"**{wrap_external(title, 'whatsapp', 120)}**"]
    aliases = contact.get("aliases") or (db_row or {}).get("aliases") or []
    if aliases:
        lines.append(
            "Também conhecido como: "
            + wrap_external(", ".join(str(a) for a in aliases), "whatsapp", 200)
        )
    phone = _format_phone_hint(jid)
    if phone:
        lines.append(f"Telefone: {phone}")

    profile = read_contact_knowledge(jid, max_chars=1200)
    if profile:
        lines.append("")
        lines.append("Perfil:")
        lines.append(wrap_external(profile, "perfil_contato", 1200))

    timeline = read_timeline_tail(jid, limit=5)
    if timeline:
        lines.append("")
        lines.append("Atividade recente:")
        for entry in timeline:
            preview = (entry.get("text_preview") or "")[:200]
            ts = entry.get("ts", "")[:16]
            lines.append(f"- {ts}: {wrap_external(preview, 'whatsapp', 220)}")

    try:
        from db import init_db, list_commitments_for_chat

        init_db()
        rows = list_commitments_for_chat(jid, limit=10)
        if rows:
            lines.append("")
            lines.append("Compromissos registrados:")
            for r in rows:
                status = r.get("status") or "?"
                ctitle = wrap_external(r.get("title") or "(sem título)", "perfil_contato", 200)
                cid = r.get("id")
                lines.append(f"- [{cid}] ({status}) {ctitle}")
    except Exception as exc:
        from services.soft_fail import soft_fail
        soft_fail("contact_tool._format_contact_block", exc)

    return lines


@tool
def list_whatsapp_contacts(limit: int = 25, refresh_from_evolution: bool = True) -> str:
    """
    List WhatsApp contacts EVI knows about (display name, not JID).
    Includes Evolution address book when refresh_from_evolution is true.
    Use when the user asks which contacts you have information on.
    """
    if refresh_from_evolution:
        try:
            sync_evolution_contacts()
        except Exception as exc:
            from services.soft_fail import soft_fail
            soft_fail("contact_tool.list_whatsapp_contacts", exc)
        collect_known_contacts()
    contacts = collect_known_contacts()[:limit]
    if not contacts:
        if not memory_enabled() and not _db_available():
            return "Memória de contatos desabilitada (EVI_CONTACT_MEMORY_DIR) e nenhum compromisso WhatsApp no banco."
        return "Nenhum contato WhatsApp conhecido ainda."

    lines = ["Contatos WhatsApp conhecidos:"]
    for c in contacts:
        try:
            from db import get_whatsapp_contact, init_db

            init_db()
            db_row = get_whatsapp_contact(c["jid"])
        except Exception:
            db_row = None
        label = format_contact_names(db_row or c, c.get("label") or "?")
        extra = []
        if c.get("commitment_count"):
            extra.append(f"{c['commitment_count']} compromisso(s)")
        if c.get("timeline_entries"):
            extra.append(f"{c['timeline_entries']} evento(s) na timeline")
        hint = f" — {', '.join(extra)}" if extra else ""
        phone = _format_phone_hint(c["jid"])
        phone_bit = f" ({phone})" if phone else ""
        lines.append(f"• {wrap_external(label, 'whatsapp', 120)}{phone_bit}{hint}")
    return "\n".join(lines)


@tool
def get_whatsapp_contact_info(name_or_phone: str) -> str:
    """
    Profile and recent WhatsApp activity for a contact by display name or phone number.
    Do NOT ask the user for JID — pass the name (e.g. Leozao) or phone (+55 16 99265-7231).
    """
    query = (name_or_phone or "").strip()
    if not query:
        return "Informe o nome ou telefone do contato."

    matches = search_contacts(query, limit=5)
    if not matches:
        return (
            f"Nenhum contato encontrado para «{query}». "
            "Use list_whatsapp_contacts para ver nomes conhecidos (inclui Evolution)."
        )
    if len(matches) > 1:
        lines = [f"Vários contatos correspondem a «{query}»:"]
        for c in matches:
            label = c.get("label") or "?"
            phone = _format_phone_hint(c["jid"])
            phone_bit = f" ({phone})" if phone else ""
            lines.append(f"• {wrap_external(label, 'whatsapp', 120)}{phone_bit}")
        lines.append("Peça detalhes de um nome específico.")
        return "\n".join(lines)

    match = matches[0]
    if match.get("from_evolution") and is_direct_jid(match["jid"]) and not read_timeline_tail(match["jid"], limit=1):
        ensure_contact(match["jid"], label=match.get("label") or query)
        backfill_contact_full(
            match["jid"],
            label=match.get("label") or query,
            days=7,
        )
        from services.commitment_replay import replay_commitments_from_evolution_log

        replay_commitments_from_evolution_log(jid=match["jid"], days=14)

    return "\n".join(_format_contact_block(match))


@tool
@guarded_write
def learn_whatsapp_contact(
    name_or_phone: str,
    days: int = 30,
    fetch_messages: bool = True,
) -> str:
    """
    Update what the EVI knows about a contact (facts and open items) by NAME or phone.
    It learns only the messages newer than the last update (the first time: the last 30 days
    stored); `days` only bounds how much history is fetched from Evolution when fetch_messages
    is true (e.g. "aprenda sobre Leozao").
    """
    return learn_contact(name_or_phone, days=days, fetch_messages=fetch_messages)


@tool
def list_recent_whatsapp_messages(days: int = 1, limit: int = 40) -> str:
    """
    List recent WhatsApp messages (NOT Gmail). Use for 'últimas mensagens do WhatsApp'.
    days=1 for today/yesterday, 7 for the past week.
    """
    return list_recent_whatsapp(days=days, limit=limit)


@tool
def summarize_whatsapp_messages(days: int = 1) -> str:
    """
    Summarize recent WhatsApp conversations (NOT email). Use for resumo do dia anterior,
    resumo da semana no WhatsApp, etc. days=1 yesterday/today, 7=week.
    """
    return summarize_whatsapp(days=days)


@tool
@guarded_write
def set_whatsapp_contact_name(
    name_or_phone: str,
    display_name: str,
    also_known_as: str = "",
) -> str:
    """
    Associate your preferred contact name (address book / agenda) with a WhatsApp contact.
    Use when the user says a person's real name differs from their WhatsApp profile name
    (e.g. «PNFagundes é Pedro Unna», «salva Leozao como Leonardo»,
    «salve o contato com final 4821 como Carla»).
    name_or_phone: existing WhatsApp name, alias, full phone or only its last digits
    (e.g. "4821"). Call the tool directly; do not ask for the full number first —
    the tool reports when the match is missing or ambiguous.
    display_name: the name the user wants to use from now on.
    also_known_as: optional comma-separated extra aliases.
    """
    query = (name_or_phone or "").strip()
    display = (display_name or "").strip()
    if not query:
        return "Informe o contato atual (nome WhatsApp ou telefone)."
    if not display:
        return "Informe o nome que deseja usar (display_name)."

    resolved, err = resolve_contact_for_query(query)
    if not resolved:
        return err
    jid, current_label = resolved
    aliases = [a.strip() for a in also_known_as.split(",") if a.strip()]
    whatsapp_label = current_label
    if current_label.casefold() == display.casefold():
        whatsapp_label = ""
    elif current_label and current_label != jid:
        if current_label.casefold() not in {display.casefold(), *(a.casefold() for a in aliases)}:
            aliases.append(current_label)

    row = assign_contact_name(
        jid,
        display_name=display,
        aliases=aliases,
        whatsapp_label=whatsapp_label or current_label,
        name_source="user",
    )
    if is_direct_jid(jid):
        ensure_contact(jid, label=display)
    title = format_contact_names(row, display)
    alias_bit = ""
    alias_list = row.get("aliases") or []
    if alias_list:
        alias_bit = f"\nAliases: {', '.join(alias_list)}"
    return f"Contato salvo no banco: {title}\nJID: {jid}{alias_bit}"


def _db_available() -> bool:
    import os

    return bool(os.getenv("DATABASE_URL", "").strip())
