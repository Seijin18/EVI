"""Channel-agnostic direct review commands (list / confirm / dismiss / today)."""

from __future__ import annotations

import json
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
_TODAY = re.compile(r"\b(hoje|agendados?\s+hoje)\b", re.I)
_CONFIRM = re.compile(
    r"\b(confirmar?|confirma|agendar?)\b\s*([\d,\s]+)",
    re.I,
)
_DISMISS = re.compile(
    r"\b(dispensar?|descartar?|ignorar?|cancelar?\s+pendente)\b\s*([\d,\s]+)",
    re.I,
)


def _parse_ids(group: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", group)]


def try_direct_review(text: str, *, confirmed_via: str = "chat") -> Optional[str]:
    """Handle list/confirm/dismiss/today without LLM."""
    stripped = text.strip()

    m = _CONFIRM.search(stripped)
    if m:
        from tools.commitment_tools import confirm_commitments

        ids = _parse_ids(m.group(2))
        if not ids:
            return "Informe os ids: confirmar 1,2"
        return confirm_commitments.invoke(
            {"commitment_ids": ids, "confirmed_via": confirmed_via}
        )

    m = _DISMISS.search(stripped)
    if m:
        from tools.commitment_tools import dismiss_commitments

        ids = _parse_ids(m.group(2))
        if not ids:
            return "Informe os ids: dispensar 1,2"
        return dismiss_commitments.invoke({"commitment_ids": ids})

    if _LIST_INTENT.search(stripped) or _PENDING.search(stripped) or _TODAY.search(stripped):
        if _TODAY.search(stripped) and not _PENDING.search(stripped):
            from tools.commitment_tools import list_scheduled_today

            return list_scheduled_today.invoke({})

        if _PENDING.search(stripped):
            from tools.commitment_tools import list_pending_commitments

            raw = list_pending_commitments.invoke({"limit": 20})
            if raw == "No pending commitments.":
                return "Nenhum compromisso pendente."
            return f"Compromissos pendentes:\n{raw}"

        from tools.calendar_tool import list_calendar_events

        return list_calendar_events.invoke({"days_ahead": 7, "limit": 25})

    return None
