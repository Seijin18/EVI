"""Backward-compatible wrappers — see commitment_review.handler."""

from __future__ import annotations

import re
from typing import Optional

from services.commitment_review.handler import try_direct_review

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


def wants_list(text: str) -> bool:
    return bool(_LIST_INTENT.search(text))


def try_direct_list(text: str) -> Optional[str]:
    return try_direct_review(text, confirmed_via="telegram")
