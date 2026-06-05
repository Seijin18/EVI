"""Heuristic priority for WhatsApp commitments."""

from __future__ import annotations

import re

_WORK = re.compile(
    r"\b(trabalho|cliente|reuni[ãa]o|call|projeto|deadline|entrega|relat[oó]rio)\b",
    re.I,
)
_UNIVERSITY = re.compile(
    r"\b(faculdade|universidade|aula|prova|estudo|tcc|disciplina)\b",
    re.I,
)
_URGENT = re.compile(
    r"\b(urgente|urgência|asap|hoje|agora|imediato)\b",
    re.I,
)


def classify_priority(text: str) -> str:
    if _URGENT.search(text):
        return "urgent"
    if _UNIVERSITY.search(text):
        return "university"
    if _WORK.search(text):
        return "work"
    return "normal"
