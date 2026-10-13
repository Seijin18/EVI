"""Blocos de formatação de item para o usuário (briefing, listas, confirmações).

Regra de UX (SCN-UX-02/03): pessoa primeiro, uma linha por item, idade/prazo curtos,
nunca marcador ``«externo»``, JID cru nem id interno. Aqui ficam só as peças puras;
quem monta a mensagem decide o formato (HTML do Telegram ou texto puro).
"""

from __future__ import annotations

import re
from datetime import date

WD_ABBR = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def short_due(d: date, today: date) -> str:
    delta = (d - today).days
    if delta < 0:
        return f"venceu {d.strftime('%d/%m')}"
    if delta == 0:
        return "até hoje"
    if delta == 1:
        return "até amanhã"
    if delta < 7:
        return f"até {WD_ABBR[d.weekday()]}"
    return f"até {d.strftime('%d/%m')}"


def short_day(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "hoje"
    if delta == 1:
        return "amanhã"
    if 1 < delta < 7:
        return WD_ABBR[d.weekday()]
    return d.strftime("%d/%m")


def short_age(hours: float) -> str:
    if hours < 1:
        return "agora"
    if hours < 24:
        return f"{int(hours)} h"
    if hours < 48:
        return "ontem"
    return f"{int(hours // 24)} d"


def who_label(name: str | None) -> str:
    """Nome para o usuário: JID/@lid cru nunca aparece."""
    name = (name or "").strip()
    if "@" not in name:
        return name
    digits = re.sub(r"\D", "", name.partition("@")[0])
    if name.endswith("@s.whatsapp.net") and digits:
        return f"+{digits}"
    return "contato sem nome"


def parse_day(value: object) -> date | None:
    """``YYYY-MM-DD[...]`` -> date; vazio/ilegível -> None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def item_line(who: str, what: str = "", when: str = "", *, n: int | None = None) -> str:
    """``[N. ]quem · o quê · quando`` em texto puro (campos vazios somem)."""
    body = " · ".join(p for p in (who, what, when) if p)
    return f"{n}. {body}" if n is not None else body
