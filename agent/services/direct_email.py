"""Direct Gmail commands without LLM (inbox summary / delete by id)."""

from __future__ import annotations

import re
from typing import Optional

_INBOX = re.compile(r"\b(caixa de entrada|inbox|gmail|e-?mail|emails?)\b", re.I)
_CHECK = re.compile(
    r"\b(verifique|verificar|revise|revisar|resumir|resumo|checar|ler|mostrar|listar|consultar)\b",
    re.I,
)
_DELETE = re.compile(r"\b(apague|apagar|deletar|excluir|remover|mover para lixeira)\b", re.I)
_MSG_ID = re.compile(r"\b([a-zA-Z0-9_-]{10,})\b")


def _extract_message_ids(text: str) -> list[str]:
    ids: list[str] = []
    for token in _MSG_ID.findall(text):
        if token.lower() in ("gmail", "email", "inbox", "apagar", "deletar"):
            continue
        if any(c.isdigit() for c in token) or len(token) >= 12:
            ids.append(token)
    return ids[:10]


def try_direct_email(text: str) -> Optional[str]:
    """Handle inbox check or delete when user mentions Gmail explicitly."""
    if not _INBOX.search(text):
        return None

    if _DELETE.search(text):
        ids = _extract_message_ids(text)
        if not ids:
            return (
                "Para apagar emails, informe o id retornado na listagem da caixa de entrada, "
                "ex.: «apagar email 18abc123def»."
            )
        from tools.email_tool import delete_emails

        return delete_emails.invoke({"message_ids": ids})

    if _CHECK.search(text):
        from tools.email_tool import summarize_inbox

        return summarize_inbox.invoke({"max_messages": 10})

    return None
