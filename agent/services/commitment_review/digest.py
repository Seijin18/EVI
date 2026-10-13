"""Format commitment digest and audit messages (channel-agnostic)."""

from __future__ import annotations

from datetime import date
from typing import List

from services.untrusted import plain_external, wrap_external
from services.ux_format import item_line, parse_day, short_day, short_due, who_label

# Duas renderizações (SCN-UX-02): ``format_*`` devolve texto marcado para o modelo/tools;
# ``format_*_user`` é o que o usuário lê (sem marcador, JID nem id interno).


class UserText(str):
    """Texto limpo para o usuário que carrega, em ``.model``, a versão marcada para o LLM.

    Respostas diretas (sem LLM) são enviadas como ``str`` normal; quem grava a memória da
    sessão usa ``.model`` para que o modelo continue vendo o conteúdo de terceiros delimitado.
    """

    model: str = ""

    def __new__(cls, user: str, model: str = ""):
        obj = super().__new__(cls, user)
        obj.model = model or str(user)
        return obj


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


def _when_user(r: dict, today: date) -> str:
    d = parse_day(r.get("event_date") or r.get("due_date"))
    if d is None:
        return ""
    return short_due(d, today) if r.get("type") == "promise" else short_day(d, today)


def format_pending_digest_user(rows: List[dict], today: date | None = None) -> str:
    """Lista de pendentes para o usuário: ``N. quem · o quê · prazo`` (N = número a digitar)."""
    from tools.calendar_time import now_local

    today = today or now_local().date()
    shown = rows[:10]
    lines = ["Compromissos pendentes para revisão:"]
    for r in shown:
        who = plain_external(who_label(r.get("source_label") or r.get("source_chat") or r.get("source")), 40)
        what = plain_external(str(r.get("title") or ""), 80)
        lines.append(item_line(who, what, _when_user(r, today), n=r["id"]))
    if len(rows) > len(shown):
        lines.append(f"+{len(rows) - len(shown)} — diga \"listar compromissos pendentes\" para ver todos")
    ids = [str(r["id"]) for r in shown]
    if len(ids) >= 2:
        lines.append(f"Responda: confirmar {ids[0]},{ids[1]} · dispensar {ids[-1]}")
    elif ids:
        lines.append(f"Responda: confirmar {ids[0]} · dispensar {ids[0]}")
    return "\n".join(lines)


def format_scheduled_today_user(rows: List[dict]) -> str:
    if not rows:
        return "Nenhum compromisso agendado hoje via EVI."
    lines = ["Compromissos agendados hoje:"]
    for r in rows:
        who = plain_external(who_label(r.get("source_label") or r.get("source_chat")), 40)
        what = plain_external(str(r.get("title") or ""), 80)
        when = str(r.get("event_time") or "")[:5]
        lines.append("• " + item_line(who, what, when))
    return "\n".join(lines)
