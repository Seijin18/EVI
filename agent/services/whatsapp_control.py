"""WhatsApp control JID: chat with EVI and run review commands."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Set

from llm import extract_llm_text
from services.commitment_review.handler import try_direct_review
from services.direct_email import try_direct_email
from services.direct_handlers import direct_handlers_enabled
from services.direct_task import try_direct_task
from services.send_result import send_outcome
from services.evolution_client import (
    format_evi_whatsapp,
    get_whatsapp_media,
    is_evi_bot_message,
    send_whatsapp_text,
)
from services.telegram_schedule import try_direct_schedule


def parse_control_jids() -> Set[str]:
    raw = os.getenv("EVI_WHATSAPP_CONTROL_JIDS", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


ChatInvoke = Callable[..., Dict[str, Any]]
ECHO_MAX_CHARS = 200
SessionHook = Callable[[str], None]


def _truncate(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _voice_fail(jid: str, session_id: str, message: str, reason: str) -> Dict[str, Any]:
    sent, send_error = send_outcome(send_whatsapp_text(jid, message, add_prefix=True))
    return {
        "result": {
            "ok": True,
            "response": format_evi_whatsapp(message),
            "session_id": session_id,
            "whatsapp_sent": sent,
            **({"send_error": send_error} if send_error else {}),
            "voice_error": reason,
        }
    }


def _transcribe_voice_note(
    *,
    jid: str,
    session_id: str,
    audio_seconds: float | None,
    audio_mime: str,
    media_key: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Return {"text": ...} on success or {"result": <reply dict>} after a visible failure."""
    from messaging.evolution import MediaTooBig
    from services import transcribe as tr

    if not tr.voice_enabled():
        return _voice_fail(jid, session_id, tr.MSG_DISABLED, tr.REASON_DISABLED)
    if audio_seconds is not None and audio_seconds > tr.max_seconds():
        fail = tr.TranscriptionResult(ok=False, reason=tr.REASON_TOO_LONG)
        return _voice_fail(jid, session_id, tr.user_message(fail), fail.reason)
    try:
        media = get_whatsapp_media(media_key or {})
    except MediaTooBig:
        fail = tr.TranscriptionResult(ok=False, reason=tr.REASON_TOO_BIG)
        return _voice_fail(jid, session_id, tr.user_message(fail), fail.reason)
    except Exception:  # noqa: BLE001
        media = None
    if not media:
        return _voice_fail(jid, session_id, tr.MSG_FAILED, "download_failed")
    audio, mime = media
    result = tr.transcribe(audio, mime or audio_mime or "audio/ogg", duration_s=audio_seconds)
    if not result.ok:
        return _voice_fail(jid, session_id, tr.user_message(result), result.reason)
    return {"text": result.text}


def process_whatsapp_control_message(
    *,
    jid: str,
    text: str,
    invoke_chat: ChatInvoke,
    reset_session: SessionHook | None = None,
    compact_session: SessionHook | None = None,
    kind: str = "text",
    audio_seconds: float | None = None,
    audio_mime: str = "audio/ogg",
    media_key: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Handle a user message from a control JID; reply via Evolution.

    kind="audio" is a voice note: it is downloaded, transcribed and then follows
    the text flow, with the reply prefixed by a "🎙️ Entendi: ..." echo line.
    """
    session_id = f"whatsapp-{jid}"
    echo = ""
    input_kind = "text"

    if kind == "audio":
        voice = _transcribe_voice_note(
            jid=jid,
            session_id=session_id,
            audio_seconds=audio_seconds,
            audio_mime=audio_mime,
            media_key=media_key,
        )
        if "result" in voice:
            return voice["result"]
        text = voice["text"]
        echo = f"🎙️ Entendi: {_truncate(text, ECHO_MAX_CHARS)}\n\n"
        input_kind = "voice"

    def _send(body: str):
        return send_whatsapp_text(jid, echo + body, add_prefix=True)

    def _fmt(body: str) -> str:
        return format_evi_whatsapp(echo + body)

    if is_evi_bot_message(text):
        return {"ok": True, "skipped": "evi_echo"}

    from services.chat_commands import try_chat_command

    cmd_reply = try_chat_command(
        text,
        session_id=session_id,
        on_reset=(lambda: reset_session(session_id)) if reset_session else None,
        on_compact=(lambda: compact_session(session_id)) if compact_session else None,
    )
    if cmd_reply:
        sent, send_error = send_outcome(_send(cmd_reply))
        return {
            "ok": True,
            "response": _fmt(cmd_reply),
            "session_id": session_id,
            "whatsapp_sent": sent,
            **({"send_error": send_error} if send_error else {}),
            "chat_command": True,
        }

    if direct_handlers_enabled():
        direct = try_direct_review(text, confirmed_via="whatsapp")
        if direct:
            reply = direct
            sent, send_error = send_outcome(_send(reply))
            return {
                "ok": True,
                "response": _fmt(reply),
                "session_id": session_id,
                "whatsapp_sent": sent,
                **({"send_error": send_error} if send_error else {}),
                "review_direct": True,
            }

        scheduled = try_direct_schedule(text)
        if scheduled:
            sent, send_error = send_outcome(_send(scheduled))
            return {
                "ok": True,
                "response": _fmt(scheduled),
                "session_id": session_id,
                "whatsapp_sent": sent,
                **({"send_error": send_error} if send_error else {}),
                "scheduled_direct": True,
            }

        tasked = try_direct_task(text)
        if tasked:
            sent, send_error = send_outcome(_send(tasked))
            return {
                "ok": True,
                "response": _fmt(tasked),
                "session_id": session_id,
                "whatsapp_sent": sent,
                **({"send_error": send_error} if send_error else {}),
                "task_direct": True,
            }

        emailed = try_direct_email(text)
        if emailed:
            sent, send_error = send_outcome(_send(emailed))
            return {
                "ok": True,
                "response": _fmt(emailed),
                "session_id": session_id,
                "whatsapp_sent": sent,
                **({"send_error": send_error} if send_error else {}),
                "email_direct": True,
            }

    try:
        result = (
            invoke_chat(text, session_id, input_kind="voice")
            if input_kind == "voice"
            else invoke_chat(text, session_id)
        )
        reply = extract_llm_text(result.get("response"))
    except Exception as exc:
        reply = f"Não consegui processar agora. Detalhe: {str(exc)[:180]}"
        result = {}

    if not reply:
        reply = (
            "Não obtive resposta do agente. Descreva o que precisa "
            "(emails, compromissos, tarefas ou calendário)."
        )

    try:
        from services.profile_updater import extract_profile_facts, merge_profile

        merge_profile(jid, extract_profile_facts(text))
    except Exception as exc:
        from services.soft_fail import soft_fail
        soft_fail("whatsapp_control.process_whatsapp_control_message", exc)

    sent, send_error = send_outcome(_send(reply))
    return {
        "ok": True,
        "response": _fmt(reply) if reply else "",
        "session_id": session_id,
        "whatsapp_sent": sent,
        **({"send_error": send_error} if send_error else {}),
        "llm": True,
        "tools": result.get("tools") or [],
    }
