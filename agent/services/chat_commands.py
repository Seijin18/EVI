"""Slash commands for control chat / Telegram — no LLM."""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Callable

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
    except Exception as exc:
        from services.soft_fail import soft_fail
        soft_fail("chat_commands._status_text", exc)
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


def _feedback_reply(session_id: str, feedback: str, note: str | None) -> str:
    """Attach /bom or /ruim feedback to the session's latest non-command turn."""
    turn_id = None
    try:
        from db import init_db, set_turn_feedback

        init_db()
        turn_id = set_turn_feedback(session_id, feedback, note)
    except Exception as exc:
        from services.soft_fail import soft_fail
        soft_fail("chat_commands._feedback_reply", exc)
    if turn_id is None:
        return "Não encontrei um pedido anterior para avaliar."
    if feedback == "bom":
        return "Anotado 👍 — obrigado pelo retorno."
    suffix = f" ({note})" if note else ""
    return f"Anotado: vou usar isso para melhorar.{suffix}"


_HELP_QUESTIONS = {
    "o que voce pode fazer",
    "o que vc pode fazer",
    "o que voce sabe fazer",
    "o que vc sabe fazer",
}


def _is_help_question(text: str) -> bool:
    folded = unicodedata.normalize("NFD", text.lower())
    folded = "".join(c for c in folded if unicodedata.category(c) != "Mn")
    folded = re.sub(r"[^a-z0-9 ]+", " ", folded)
    return " ".join(folded.split()) in _HELP_QUESTIONS


def try_chat_command(
    text: str,
    *,
    session_id: str,
    on_compact: CompactFn | None = None,
    on_reset: Callable[[], None] | None = None,
) -> str | None:
    """Return reply text if message is a slash command, else None."""
    raw = (text or "").strip()
    if _is_help_question(raw):
        from services.help_text import build_help

        return build_help()
    if not raw.startswith("/"):
        return None
    cmd = raw.split()[0].lower()
    if cmd in ("/ajuda", "/help"):
        from services.help_text import build_help

        return build_help()
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
    if cmd in ("/bom", "/ruim"):
        note = raw[len(cmd):].strip() or None
        return _feedback_reply(session_id, cmd[1:], note)
    if cmd in ("/memoria", "/memory"):
        return _memoria_text()
    return None
