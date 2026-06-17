"""WhatsApp contact lookup by name or phone — no JID required from the user."""

from __future__ import annotations

from langchain_core.tools import tool

from services.contact_filesystem import (
    collect_known_contacts,
    memory_enabled,
    read_profile_excerpt,
    read_timeline_tail,
    search_contacts,
)
from services.contact_learning import learn_contact


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
    lines = [f"**{label}**"]
    phone = _format_phone_hint(jid)
    if phone:
        lines.append(f"Telefone: {phone}")

    profile = read_profile_excerpt(jid, max_chars=1200)
    if profile:
        lines.append("")
        lines.append("Perfil:")
        lines.append(profile)

    timeline = read_timeline_tail(jid, limit=5)
    if timeline:
        lines.append("")
        lines.append("Atividade recente:")
        for entry in timeline:
            preview = (entry.get("text_preview") or "")[:200]
            ts = entry.get("ts", "")[:16]
            lines.append(f"- {ts}: {preview}")

    try:
        from db import init_db, list_commitments_for_chat

        init_db()
        rows = list_commitments_for_chat(jid, limit=10)
        if rows:
            lines.append("")
            lines.append("Compromissos registrados:")
            for r in rows:
                status = r.get("status") or "?"
                title = r.get("title") or "(sem título)"
                cid = r.get("id")
                lines.append(f"- [{cid}] ({status}) {title}")
    except Exception:
        pass

    return lines


@tool
def list_whatsapp_contacts(limit: int = 25) -> str:
    """
    List WhatsApp contacts EVI knows about (display name, not JID).
    Use when the user asks which contacts you have information on.
    """
    contacts = collect_known_contacts()[:limit]
    if not contacts:
        if not memory_enabled() and not _db_available():
            return "Memória de contatos desabilitada (EVI_CONTACT_MEMORY_DIR) e nenhum compromisso WhatsApp no banco."
        return "Nenhum contato WhatsApp conhecido ainda."

    lines = ["Contatos WhatsApp conhecidos:"]
    for c in contacts:
        label = c.get("label") or "?"
        extra = []
        if c.get("commitment_count"):
            extra.append(f"{c['commitment_count']} compromisso(s)")
        if c.get("timeline_entries"):
            extra.append(f"{c['timeline_entries']} evento(s) na timeline")
        hint = f" — {', '.join(extra)}" if extra else ""
        phone = _format_phone_hint(c["jid"])
        phone_bit = f" ({phone})" if phone else ""
        lines.append(f"• {label}{phone_bit}{hint}")
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
            "Use list_whatsapp_contacts para ver nomes conhecidos."
        )
    if len(matches) > 1:
        lines = [f"Vários contatos correspondem a «{query}»:"]
        for c in matches:
            label = c.get("label") or "?"
            phone = _format_phone_hint(c["jid"])
            phone_bit = f" ({phone})" if phone else ""
            lines.append(f"• {label}{phone_bit}")
        lines.append("Peça detalhes de um nome específico.")
        return "\n".join(lines)

    return "\n".join(_format_contact_block(matches[0]))


@tool
def learn_whatsapp_contact(
    name_or_phone: str,
    days: int = 30,
    fetch_messages: bool = True,
) -> str:
    """
    Read WhatsApp chat history for a contact (Evolution API) and synthesize learning.
    Use when the user asks to learn/study a contact over N days by NAME or phone
    (e.g. "aprenda sobre Leozao nos últimos 30 dias"). fetch_messages: pull chat from Evolution first.
    """
    return learn_contact(name_or_phone, days=days, fetch_messages=fetch_messages)


def _db_available() -> bool:
    import os

    return bool(os.getenv("DATABASE_URL", "").strip())
