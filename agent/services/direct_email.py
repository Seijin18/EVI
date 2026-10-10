"""Direct Gmail commands without LLM (inbox summary). Deletion goes through the chat turn."""

from __future__ import annotations

import re
from typing import Optional

_INBOX = re.compile(r"\b(caixa de entrada|inbox|gmail|e-?mail|emails?)\b", re.I)
_CHECK = re.compile(
    r"\b(verifique|verificar|revise|revisar|resumir|resumo|checar|ler|mostrar|listar|consultar)\b",
    re.I,
)
_DELETE = re.compile(r"\b(apague|apagar|deletar|excluir|remover|mover para lixeira)\b", re.I)


def try_direct_email(text: str) -> Optional[str]:
    """Handle inbox check or delete when user mentions Gmail explicitly."""
    if not _INBOX.search(text):
        return None

    if _DELETE.search(text):
        # No direct delete path: deletion is two-step and only runs inside a chat
        # turn (write_guard), so hand the request to the agent instead.
        return None

    if _CHECK.search(text):
        from tools.email_tool import summarize_inbox

        return summarize_inbox.invoke({"max_messages": 10})

    return None
