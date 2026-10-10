"""Format commitment digest and audit messages (channel-agnostic)."""

from __future__ import annotations

from typing import List

from services.untrusted import wrap_external


def format_pending_digest(rows: List[dict]) -> str:
    lines = ["EVI: compromissos pendentes para revisão:"]
    for r in rows[:10]:
        pr = r.get("priority", "normal")
        src = r.get("source_label") or r.get("source_chat") or r.get("source", "")
        text = f"{r['title']} ({src})" if src else str(r["title"])
        lines.append(
            f"• [{r['id']}] ({pr}) {wrap_external(text, 'whatsapp', 200)} — "
            f"{r.get('event_date') or r.get('due_date') or 'sem data'}"
        )
    lines.append(
        "Comandos: listar compromissos pendentes | confirmar 1,2 | dispensar 3"
    )
    return "\n".join(lines)


def format_scheduled_today(rows: List[dict]) -> str:
    if not rows:
        return "Nenhum compromisso agendado hoje via EVI."
    lines = ["EVI: compromissos agendados hoje:"]
    for r in rows:
        src = r.get("source_label") or r.get("source_chat") or "?"
        via = r.get("confirmed_via") or "?"
        when = r.get("event_time") or r.get("event_date") or r.get("due_date") or ""
        item = wrap_external(f"{r['title']} — origem: {src}", "whatsapp", 200)
        lines.append(f"• {item} {when} — via: {via}")
    return "\n".join(lines)
