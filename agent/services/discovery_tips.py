"""Dica de descoberta do briefing da manhã (evi-discovery-tips): uma capacidade que o
usuário ainda não usou nos últimos dias, com uma frase de exemplo pronta para copiar.

Determinístico, sem LLM. O uso vem do ``turn_log`` (``db.capabilities_used_since``): nomes de
tools chamadas e ``input_kind:<tipo>``. Qualquer falha de banco vira "sem dica".
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import NamedTuple

from services.soft_fail import soft_fail

USED_WINDOW_DAYS = 14


class Tip(NamedTuple):
    id: str
    marker: str  # entrada de ``capabilities_used_since`` que prova que a capacidade foi usada
    text: str


TIPS: tuple[Tip, ...] = (
    Tip("reminder", "create_reminder",
        '💡 Dica: diga "me lembra às 18h de pagar o boleto" e eu aviso aqui.'),
    Tip("voice", "input_kind:voice", "💡 Dica: pode mandar áudio — eu entendo."),
    Tip("contact", "get_whatsapp_contact_info",
        '💡 Dica: pergunte "o que você sabe sobre a Ana?"'),
    Tip("buttons", "input_kind:button",
        "💡 Dica: toque ✅ ou ✖ nos itens para resolver sem digitar."),
)


def tips_enabled() -> bool:
    return os.getenv("EVI_BRIEFING_TIPS", "true").strip().lower() != "false"


def pick_tip(today: date, used: set[str]) -> str | None:
    """Rotates daily (by date ordinal) among the capabilities not in ``used``."""
    unused = [t for t in TIPS if t.marker not in used]
    if not unused:
        return None
    return unused[today.toordinal() % len(unused)].text


def tip_for(today: date, now: datetime | None = None) -> str | None:
    """The tip line for the morning briefing, or None (flag off, all used, DB failure)."""
    if not tips_enabled():
        return None
    try:
        import db
        from tools.calendar_time import now_local

        since = (now or now_local()) - timedelta(days=USED_WINDOW_DAYS)
        return pick_tip(today, db.capabilities_used_since(since))
    except Exception as exc:
        soft_fail("discovery_tips.tip_for", exc)
        return None
