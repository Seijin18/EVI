"""Direct list/review for Telegram (Calendar events or pending WhatsApp commitments)."""

from __future__ import annotations

import re
from typing import Optional

_LIST_INTENT = re.compile(
    r"\b("
    r"revise|revisar|review|listar|lista|liste|listem|mostrar|mostre|ver|quais|"
    r"me\s+diga|me\s+mostre"
    r")\b.*\b("
    r"agendamento|agendamentos|compromisso|compromissos|evento|eventos|"
    r"calend[aá]rio|agenda"
    r")\b",
    re.I,
)
_PENDING = re.compile(r"\bpendente?s?\b", re.I)


def wants_list(text: str) -> bool:
    return bool(_LIST_INTENT.search(text))


def try_direct_list(text: str) -> Optional[str]:
    """List calendar events or pending commitments without LLM."""
    if not wants_list(text):
        return None

    if _PENDING.search(text):
        from tools.commitment_tools import list_pending_commitments

        raw = list_pending_commitments.invoke({"limit": 20})
        if raw == "No pending commitments.":
            return "Nenhum compromisso pendente do WhatsApp."
        return f"Compromissos pendentes (WhatsApp):\n{raw}"

    from tools.calendar_tool import list_calendar_events

    return list_calendar_events.invoke({"days_ahead": 7, "limit": 25})
