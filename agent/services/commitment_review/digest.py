"""Format commitment digest and audit messages (channel-agnostic)."""

from __future__ import annotations

from typing import List


def format_pending_digest(rows: List[dict]) -> str:
    lines = ["EVI: compromissos pendentes para revisão:"]
    for r in rows[:10]:
        pr = r.get("priority", "normal")
        src = r.get("source_label") or r.get("source_chat") or r.get("source", "")
        src_bit = f" ({src})" if src else ""
        lines.append(
            f"• [{r['id']}] ({pr}) {r['title']} — "
            f"{r.get('event_date') or r.get('due_date') or 'sem data'}{src_bit}"
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
        lines.append(f"• {r['title']} {when} — origem: {src} — via: {via}")
    return "\n".join(lines)
