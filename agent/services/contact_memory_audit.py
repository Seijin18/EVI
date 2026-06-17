"""Audit contact filesystem memory for /memoria and health."""

from __future__ import annotations

import os
from pathlib import Path

from services.contact_filesystem import collect_known_contacts, memory_enabled, memory_root


def format_memory_audit(*, limit: int = 15) -> str:
    if not memory_enabled():
        return (
            "Memória de contatos **desabilitada** — configure EVI_CONTACT_MEMORY_DIR "
            "e monte o volume no agent-api."
        )
    root = memory_root()
    if not root.is_dir():
        return f"Diretório de memória não existe: {root}"

    contacts = collect_known_contacts()[:limit]
    lines = [
        f"Memória de contatos ({root})",
        f"Total conhecidos: {len(collect_known_contacts())}",
        "",
    ]
    if not contacts:
        lines.append("(nenhum contato ainda — ingerir WhatsApp ou learn_whatsapp_contact)")
        return "\n".join(lines)

    for c in contacts:
        label = c.get("label") or "?"
        jid = c.get("jid") or ""
        tl = c.get("timeline_entries") or 0
        commits = c.get("commitment_count") or 0
        synth = _last_synthesis_heading(jid)
        synth_bit = f" | síntese: {synth}" if synth else ""
        lines.append(f"• {label} — timeline: {tl}, compromissos: {commits}{synth_bit}")
    return "\n".join(lines)


def _last_synthesis_heading(jid: str) -> str:
    try:
        from services.contact_filesystem import contact_dir

        profile = contact_dir(jid) / "profile.md"
        if not profile.is_file():
            return ""
        for line in profile.read_text(encoding="utf-8").splitlines():
            if line.startswith("## Síntese ("):
                return line[3:].strip()
    except Exception:
        pass
    return ""


def contact_memory_health() -> dict[str, object]:
    enabled = memory_enabled()
    out: dict[str, object] = {"enabled": enabled, "ok": enabled}
    if not enabled:
        out["detail"] = "EVI_CONTACT_MEMORY_DIR unset"
        return out
    try:
        root = memory_root()
        out["path"] = str(root)
        out["ok"] = root.is_dir()
        out["contact_count"] = len(collect_known_contacts())
    except Exception as exc:
        out["ok"] = False
        out["detail"] = str(exc)[:200]
    return out
