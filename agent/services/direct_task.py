"""Direct Google Tasks creation when the LLM skips tool calls."""

from __future__ import annotations

import re
from typing import Optional

_TASK_INTENT = re.compile(
    r"\b("
    r"crie?\s+(uma\s+)?(tarefa|task)|criar\s+(uma\s+)?(tarefa|task)|"
    r"nova\s+(tarefa|task)|adiciona?\s+(uma\s+)?(tarefa|task)|"
    r"pode\s+criar\s+(uma\s+)?(tarefa|task)"
    r")\b",
    re.I,
)
_QUOTED = re.compile(r'["\'\u201c\u201d]([^"\'\u201c\u201d]+)["\'\u201c\u201d]')
_TITLE_TAIL = re.compile(
    r"(?:tarefa|task)\s+(?:de\s+)?(?:teste\s+)?(?:chamada\s+)?(.+?)(?:\?|$)",
    re.I,
)


def wants_task(text: str) -> bool:
    return bool(_TASK_INTENT.search(text))


def _parse_title(text: str) -> str:
    m = _QUOTED.search(text)
    if m:
        return m.group(1).strip()[:120]
    m = _TITLE_TAIL.search(text)
    if m:
        title = m.group(1).strip(" ?.")
        if title and len(title) > 2:
            return title[:120]
    if re.search(r"\bteste\b", text, re.I):
        return "Tarefa de teste"
    return "Tarefa EVI"


def try_direct_task(text: str) -> Optional[str]:
    if not wants_task(text):
        return None
    from tools.task_tool import create_task

    title = _parse_title(text)
    return create_task.invoke(
        {
            "title": title,
            "due_date": "",
            "notes": text[:200],
        }
    )
