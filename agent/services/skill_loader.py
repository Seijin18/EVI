"""Selective runtime skill injection (OpenClaw-style)."""

from __future__ import annotations

import re
from pathlib import Path

from services.workspace import workspace_root

_SKILL_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(email|emails?|gmail|inbox|caixa de entrada|aliexpress|olx|apagar|excluir)\b",
            re.I,
        ),
        "inbox-triage",
    ),
    (
        re.compile(
            r"\b(compromisso|compromissos|pendente|agenda|confirmar|dispensar|calend[aá]rio)\b",
            re.I,
        ),
        "commitment-review",
    ),
]

_MAX_SKILL_CHARS = 2500


def _skill_path(skill_id: str) -> Path:
    return workspace_root() / "skills" / skill_id / "SKILL.md"


def match_skills(user_message: str) -> list[str]:
    matched: list[str] = []
    for pattern, skill_id in _SKILL_RULES:
        if pattern.search(user_message) and skill_id not in matched:
            matched.append(skill_id)
    return matched


def load_skill_content(skill_id: str) -> str:
    path = _skill_path(skill_id)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) > _MAX_SKILL_CHARS:
        return text[:_MAX_SKILL_CHARS] + "\n…"
    return text


def build_skills_block(user_message: str) -> str:
    parts: list[str] = []
    for skill_id in match_skills(user_message):
        content = load_skill_content(skill_id)
        if content:
            parts.append(f"## Skill: {skill_id}\n{content}")
    if not parts:
        return ""
    return "RUNTIME SKILLS:\n" + "\n\n".join(parts)
