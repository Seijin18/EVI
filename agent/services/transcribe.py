"""Voice-note transcription (evi-voice-input): audio bytes -> text via Gemini.

The text then enters the graph as if the user had typed it. Failures never raise:
they come back as a `TranscriptionResult` with a `reason` and a pt-BR message
(`user_message`) the channel handlers send instead of staying silent.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from dataclasses import dataclass

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

MAX_BYTES = 20 * 1024 * 1024  # Telegram Bot API download limit
MAX_TEXT_CHARS = 2000
DEFAULT_MAX_SECONDS = 300

REASON_DISABLED = "disabled"
REASON_UNSUPPORTED_PROVIDER = "unsupported_provider"
REASON_TOO_LONG = "too_long"
REASON_TOO_BIG = "too_big"
REASON_EMPTY = "empty"
REASON_FAILED = "failed"

MSG_DISABLED = "Mensagens de voz estão desativadas."
MSG_UNSUPPORTED_PROVIDER = "Áudio não é suportado neste modo."
MSG_EMPTY = "Não consegui entender o áudio, pode repetir?"
MSG_FAILED = "Não consegui ouvir o áudio agora."

_INSTRUCTION = (
    "Transcreva literalmente, em português, o áudio a seguir. "
    "Responda somente com a transcrição, sem comentários, aspas ou explicações. "
    "Se não houver fala, não responda nada."
)


@dataclass(frozen=True)
class TranscriptionResult:
    ok: bool
    text: str = ""
    reason: str = ""


def voice_enabled() -> bool:
    return os.getenv("EVI_VOICE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def max_seconds() -> int:
    raw = os.getenv("EVI_VOICE_MAX_SECONDS", "").strip()
    try:
        value = int(raw) if raw else DEFAULT_MAX_SECONDS
    except ValueError:
        logger.warning("EVI_VOICE_MAX_SECONDS=%r is not an integer; using %d", raw, DEFAULT_MAX_SECONDS)
        return DEFAULT_MAX_SECONDS
    return value if value > 0 else DEFAULT_MAX_SECONDS


def _too_long_message() -> str:
    minutes = max(1, round(max_seconds() / 60))
    return f"O áudio passa de {minutes} min; mande um mais curto ou escreva."


def _too_big_message() -> str:
    return f"O áudio passa de {MAX_BYTES // (1024 * 1024)} MB; mande um mais curto ou escreva."


def user_message(result: TranscriptionResult) -> str:
    """pt-BR text to send the user for a failed result ('' when the result is ok)."""
    if result.ok:
        return ""
    return {
        REASON_DISABLED: MSG_DISABLED,
        REASON_UNSUPPORTED_PROVIDER: MSG_UNSUPPORTED_PROVIDER,
        REASON_TOO_LONG: _too_long_message(),
        REASON_TOO_BIG: _too_big_message(),
        REASON_EMPTY: MSG_EMPTY,
    }.get(result.reason, MSG_FAILED)


def _fail(reason: str) -> TranscriptionResult:
    return TranscriptionResult(ok=False, text="", reason=reason)


def _provider_supports_audio() -> bool:
    from llm import _is_sim_provider, _llm_provider

    provider = _llm_provider()
    return provider == "gemini" or _is_sim_provider(provider)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:MAX_TEXT_CHARS].strip()


def transcribe(audio: bytes, mime: str, *, duration_s: float | None = None) -> TranscriptionResult:
    if not voice_enabled():
        return _fail(REASON_DISABLED)
    if not _provider_supports_audio():
        return _fail(REASON_UNSUPPORTED_PROVIDER)
    if duration_s is not None and duration_s > max_seconds():
        return _fail(REASON_TOO_LONG)
    if len(audio or b"") > MAX_BYTES:
        return _fail(REASON_TOO_BIG)
    if not audio:
        return _fail(REASON_EMPTY)

    try:
        from llm import build_llm, extract_llm_text

        message = HumanMessage(
            content=[
                {"type": "text", "text": _INSTRUCTION},
                {"type": "media", "mime_type": mime, "data": base64.b64encode(audio).decode("ascii")},
            ]
        )
        response = build_llm().invoke([message])
        text = _clean(extract_llm_text(response.content))
    except Exception:
        logger.exception("voice transcription failed")
        return _fail(REASON_FAILED)

    if not text:
        return _fail(REASON_EMPTY)
    return TranscriptionResult(ok=True, text=text)
