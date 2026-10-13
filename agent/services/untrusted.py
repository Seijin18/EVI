"""Delimita conteúdo de terceiros (e-mail, WhatsApp, perfil de contato) como dado.

Todo texto que não é do usuário e vai parar num prompt de LLM passa por
``wrap_external``: o bloco ``«externo:<fonte>» … «/externo»`` sinaliza ao modelo
que o conteúdo é dado, nunca instrução. Marcadores presentes no próprio texto
são removidos para que ele não consiga "fechar" o bloco antes da hora.
"""

from __future__ import annotations

import re
import unicodedata

OPEN_FMT = "«externo:{source}»"
CLOSE = "«/externo»"
TRUNC_MARK = "…[truncado]"
EMPTY_MARK = "(vazio)"

# Marcador completo (aberto/fechado), com variações de caixa/espaço e sósias ASCII
# (<<externo>>, [externo:x], «  / EXTERNO »).
_MARKER_RE = re.compile(
    r"[«<\[‹]{1,2}\s*/?\s*externo\b[^»>\]›\n]*[»>\]›]{1,2}",
    re.IGNORECASE,
)
# Só os marcadores que ``wrap_external`` emite («externo:fonte» / «/externo»); sem sósias ASCII.
_WRAP_MARKER_RE = re.compile(r"«\s*/?\s*externo(?::[\w.\-]*)?\s*»", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f​-‏  ‪-‮⁠⁡⁢⁣⁤᠎﻿]")
_SOURCE_BAD_RE = re.compile(r"[^a-z0-9_-]")


def _clean_source(source: str | None) -> str:
    cleaned = _SOURCE_BAD_RE.sub("", (source or "").lower())
    return cleaned[:40] or "desconhecido"


def _neutralize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    # Remover um marcador pode juntar pedaços de outro: repete até estabilizar.
    for _ in range(10):
        cleaned = _MARKER_RE.sub("", text)
        if cleaned == text:
            break
        text = cleaned
    text = text.replace("«", "‹").replace("»", "›")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def wrap_external(text: str | None, source: str, max_chars: int = 500) -> str:
    """Envolve ``text`` em ``«externo:source» … «/externo»``.

    Remove marcadores do conteúdo, caracteres de controle (exceto ``\\n``/``\\t``)
    e trunca em ``max_chars`` (marcando com ``…[truncado]``).
    """
    open_marker = OPEN_FMT.format(source=_clean_source(source))
    body = _neutralize(str(text)) if text else ""
    if not body:
        return f"{open_marker} {EMPTY_MARK} {CLOSE}"
    if max_chars > 0 and len(body) > max_chars:
        body = body[:max_chars].rstrip() + TRUNC_MARK
    return f"{open_marker}{_sep(body)}{body}{_sep(body)}{CLOSE}"


def _sep(body: str) -> str:
    return "\n" if "\n" in body else " "


def has_marker(text: str | None) -> bool:
    """True se ``text`` ainda contém um marcador ``«externo:…»`` / ``«/externo»``."""
    return bool(text) and _WRAP_MARKER_RE.search(text) is not None


def strip_markers(text: str | None) -> str:
    """Remove os marcadores de ``wrap_external`` e nada mais (conteúdo entre eles fica)."""
    out = text or ""
    for _ in range(10):  # remover um marcador pode juntar pedaços de outro
        cleaned = _WRAP_MARKER_RE.sub("", out)
        if cleaned == out:
            break
        out = cleaned
    return out


def plain_external(text: str | None, max_chars: int = 120) -> str:
    """Texto de terceiros para o USUÁRIO: sem marcadores/controle, numa linha só.

    Não escapa para nenhum formato (quem monta a mensagem escapa). Corta em palavra
    com ``…`` quando passa de ``max_chars``.
    """
    body = " ".join(_neutralize(str(text)).split()) if text else ""
    if max_chars > 0 and len(body) > max_chars:
        cut = body[:max_chars]
        if " " in cut and body[max_chars] != " ":
            cut = cut[: cut.rfind(" ")]
        body = cut.rstrip(" ,.;:-") + "…"
    return body
