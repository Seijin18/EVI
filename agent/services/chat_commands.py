"""Slash commands for control chat / Telegram — no LLM."""

from __future__ import annotations

import os
from typing import Any, Callable

CompactFn = Callable[[], None]


def _status_text() -> str:
    from services.health import run_health_checks

    checks = run_health_checks(graph_ready=True)
    llm = os.getenv("EVI_LLM_PROVIDER", "ollama")
    embed = os.getenv("EVI_EMBED_PROVIDER", "ollama")
    pending = 0
    try:
        from db import count_unnotified_pending, init_db

        init_db()
        pending = count_unnotified_pending()
    except Exception:
        pass
    mem = "on" if os.getenv("EVI_CONTACT_MEMORY_DIR", "").strip() else "off"
    hb = "on" if os.getenv("EVI_HEARTBEAT_ENABLED", "").lower() in ("1", "true", "yes") else "off"
    ok = checks.get("ok", False)
    lines = [
        "EVI status",
        f"- health: {'ok' if ok else 'degraded'}",
        f"- LLM: {llm} | embed: {embed}",
        f"- contact memory: {mem}",
        f"- heartbeat: {hb}",
        f"- pending unnotified: {pending}",
    ]
    return "\n".join(lines)


def _memoria_text() -> str:
    from services.contact_memory_audit import format_memory_audit

    return format_memory_audit()


def try_chat_command(
    text: str,
    *,
    session_id: str,
    on_compact: CompactFn | None = None,
    on_reset: Callable[[], None] | None = None,
) -> str | None:
    """Return reply text if message is a slash command, else None."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    cmd = raw.split()[0].lower()
    if cmd in ("/status", "/estado"):
        return _status_text()
    if cmd in ("/reset", "/new"):
        if on_reset:
            on_reset()
        return "Sessão reiniciada (memória curta limpa)."
    if cmd in ("/compact", "/compactar"):
        if on_compact:
            on_compact()
        return "Memória compactada (flush + trim aplicado)."
    if cmd in ("/memoria", "/memory"):
        return _memoria_text()
    return None
