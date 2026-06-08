"""Auto-update per-contact profile.md from chat messages (Etapa 9)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_NAME_RE = re.compile(
    r"\b(?:meu\s+nome\s+[eé]|me\s+chamo|sou\s+(?:o|a)\s+)\s*([A-ZÀ-Ü][a-zA-ZÀ-ÿ]+(?:\s+[A-ZÀ-Ü][a-zA-ZÀ-ÿ]+)*)",
    re.I,
)
_COMPANY_RE = re.compile(
    r"\b(?:trabalho\s+(?:na|no|em|para\s+a?|pela?)\s+|empresa\s+[eé]\s+|empresa:\s*)([A-ZÀ-Ü][A-Za-zÀ-ÿ0-9\s&.,-]{1,50}?)(?:\.|,|$|\s{2})",
    re.I,
)
_ROLE_RE = re.compile(
    r"\b(?:sou\s+(?:o|a)?\s*|meu\s+cargo\s+[eé]\s+|cargo:\s*)([A-ZÀ-Üa-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+){0,3})\b",
    re.I,
)
_ROLE_KEYWORDS = {
    "engenheiro", "desenvolvedor", "gerente", "diretor", "analista",
    "designer", "coordenador", "CEO", "CTO", "CFO", "consultor",
}


def extract_profile_facts(text: str) -> dict[str, str]:
    """Extract name, company, role from free text."""
    facts: dict[str, str] = {}
    m = _NAME_RE.search(text)
    if m:
        facts["name"] = m.group(1).strip()
    m = _COMPANY_RE.search(text)
    if m:
        facts["company"] = m.group(1).strip().rstrip(".,")
    m = _ROLE_RE.search(text)
    if m:
        candidate = m.group(1).strip().lower()
        if any(kw in candidate for kw in _ROLE_KEYWORDS):
            facts["role"] = m.group(1).strip().capitalize()
    return facts


def _contact_root(jid: str) -> Path | None:
    base = os.getenv("EVI_CONTACT_MEMORY_DIR", "").strip()
    if not base:
        return None
    return Path(base) / jid


def merge_profile(jid: str, facts: dict[str, str]) -> bool:
    """Merge extracted facts into contact's profile.md; return True if updated."""
    if not facts:
        return False
    root = _contact_root(jid)
    if root is None:
        return False
    root.mkdir(parents=True, exist_ok=True)
    profile_path = root / "profile.md"
    existing: dict[str, str] = {}
    if profile_path.is_file():
        for line in profile_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("- **") and ":**" in line:
                key_part, _, val_part = line.partition(":**")
                key = key_part.lstrip("- **").strip().lower()
                existing[key] = val_part.strip()
    _KEY_LABEL = {"name": "Name", "company": "Company", "role": "Role"}
    updated = False
    for fact_key, fact_val in facts.items():
        label = _KEY_LABEL.get(fact_key, fact_key.capitalize())
        old = existing.get(fact_key.lower())
        if old != fact_val:
            existing[fact_key.lower()] = fact_val
            updated = True
    if not updated:
        return False
    lines = [f"# Perfil {jid}", ""]
    for key, val in existing.items():
        label = _KEY_LABEL.get(key, key.capitalize())
        lines.append(f"- **{label}:** {val}")
    profile_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
