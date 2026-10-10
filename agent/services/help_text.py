"""Deterministic /ajuda text — no LLM. Lists only features that are switched on."""

from __future__ import annotations

import os


def _on(name: str) -> bool:
    # Read at call time so tests/ops can flip flags without a restart.
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def build_help() -> str:
    lines = [
        "O que eu faço — é só pedir, por exemplo:",
        "• Marca reunião amanhã às 10h com a Ana",
        "• O que tenho amanhã?",
        "• Cria tarefa: pagar o boleto até sexta",
        "• Resume meus e-mails / Apaga as promoções",
    ]
    if _on("EVI_REPLY_DEBTS_ENABLED"):
        lines.append("• Quem está esperando minha resposta?")
    if _on("EVI_REMINDERS_ENABLED"):
        lines.append("• Me lembra às 18h de ligar para o banco")
    if _on("EVI_BRIEFING_ENABLED"):
        lines.append("• Confirma 2 (depois do briefing da manhã)")
    if _on("EVI_VOICE_ENABLED"):
        lines.append("• 🎙️ Pode mandar áudio")
    lines.append("/bom e /ruim avaliam a última resposta · /reset recomeça a conversa")
    return "\n".join(lines)
