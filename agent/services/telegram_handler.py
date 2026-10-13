"""Shared Telegram update → chat → reply logic (webhook and polling)."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict

from llm import extract_llm_text
from services.direct_handlers import direct_handlers_enabled
from services.telegram_audit import log_telegram_turn
from services.telegram_format import format_for_telegram
from services.commitment_review.handler import try_direct_review
from services.telegram_notify import send_telegram_message
from services.direct_email import try_direct_email
from services.direct_task import try_direct_task
from services.telegram_schedule import try_direct_schedule

ChatInvoke = Callable[[str, str], Dict[str, Any]]

_log = logging.getLogger(__name__)
_warned_open = False


def _chat_allowed(chat_id: Any) -> bool:
    """Only the owner's chat (TELEGRAM_CHAT_ID + optional TELEGRAM_ALLOWED_CHAT_IDS)."""
    global _warned_open
    owner = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not owner:
        if not _warned_open:
            _warned_open = True
            _log.warning("TELEGRAM_CHAT_ID not set; rejecting all Telegram chats (fail-closed)")
        return False
    allowed = {owner}
    allowed.update(
        p.strip() for p in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if p.strip()
    )
    return str(chat_id).strip() in allowed


def _persist_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    try:
        from db import init_db, save_message

        init_db()
        save_message(session_id, "user", user_text)
        save_message(session_id, "assistant", assistant_text)
    except Exception as exc:
        from services.soft_fail import soft_fail
        soft_fail("telegram_handler._persist_turn", exc)


def _reply_direct(
    *,
    session_id: str,
    chat_id: Any,
    text: str,
    ai_content: str,
    tools: list,
    extra: Dict[str, Any] | None = None,
    reply_prefix: str = "",
) -> Dict[str, Any]:
    from services.send_result import EMPTY_TEXT, send_outcome

    ai_content = format_for_telegram(extract_llm_text(ai_content))
    outgoing = f"{reply_prefix}{ai_content}" if ai_content else ""
    result = send_telegram_message(outgoing, chat_id=chat_id) if outgoing else False
    sent, reason = send_outcome(result)
    if not ai_content:
        reason = EMPTY_TEXT
    _persist_turn(session_id, text, ai_content)
    log_telegram_turn(
        session_id,
        text,
        ai_content,
        tools,
        telegram_sent=sent,
    )
    out: Dict[str, Any] = {
        "ok": True,
        "response": outgoing,
        "session_id": session_id,
        "telegram_sent": sent,
    }
    if reason:
        # Why the reply was dropped — telegram_sent alone said nothing.
        out["send_error"] = reason
    if extra:
        out.update(extra)
    return out


_ECHO_MAX_CHARS = 200


def _voice_attachment(message: Dict[str, Any]) -> tuple[Dict[str, Any], str] | None:
    voice = message.get("voice")
    if isinstance(voice, dict):
        return voice, voice.get("mime_type") or "audio/ogg"
    audio = message.get("audio")
    if isinstance(audio, dict):
        return audio, audio.get("mime_type") or "audio/mpeg"
    return None


def _voice_turn(
    message: Dict[str, Any],
    attachment: tuple[Dict[str, Any], str],
    invoke_chat: ChatInvoke,
) -> Dict[str, Any]:
    """Voice note -> transcription -> chat(); every outcome produces a visible reply."""
    import os

    from services import transcribe as tr

    chat_id = (message.get("chat") or {}).get("id", "telegram")
    session_id = f"telegram-{chat_id}"

    def fail(msg: str, detail: str = "") -> Dict[str, Any]:
        return _reply_direct(
            session_id=session_id,
            chat_id=chat_id,
            text="[voice]",
            ai_content=msg,
            tools=[{"type": "error", "detail": detail[:500]}] if detail else [],
            extra={"voice": True, "voice_error": detail or msg},
        )

    try:
        if not tr.voice_enabled():
            return fail(tr.MSG_DISABLED)
        meta, mime = attachment
        duration = meta.get("duration")
        if isinstance(duration, (int, float)) and duration > tr.max_seconds():
            return fail(tr.user_message(tr.TranscriptionResult(False, "", tr.REASON_TOO_LONG)))
        size = meta.get("file_size")
        if isinstance(size, (int, float)) and size > tr.MAX_BYTES:
            return fail(tr.user_message(tr.TranscriptionResult(False, "", tr.REASON_TOO_BIG)))

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        from services.telegram_poller import _scrub, download_file, get_file_path

        try:
            audio = download_file(token, get_file_path(token, str(meta.get("file_id", ""))), tr.MAX_BYTES)
        except Exception as exc:
            return fail(tr.MSG_FAILED, _scrub(exc, token))

        result = tr.transcribe(
            audio, mime, duration_s=float(duration) if isinstance(duration, (int, float)) else None
        )
        if not result.ok:
            return fail(tr.user_message(result), result.reason)

        text = result.text
        echo = text if len(text) <= _ECHO_MAX_CHARS else text[:_ECHO_MAX_CHARS].rstrip() + "…"
        prefix = f"🎙️ Entendi: {echo}\n\n"
        try:
            reply = invoke_chat(text, session_id, input_kind="voice")  # type: ignore[call-arg]
        except Exception as exc:
            detail = str(exc)
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content="Não consegui processar sua mensagem agora. " f"Detalhe: {detail[:180]}",
                tools=[{"type": "error", "detail": detail[:500]}],
                extra={"error": True, "voice": True},
                reply_prefix=prefix,
            )
        tools = reply.get("tools") or reply.get("output_messages") or []
        return _reply_direct(
            session_id=session_id,
            chat_id=chat_id,
            text=text,
            ai_content=reply.get("response") or "",
            tools=tools if isinstance(tools, list) else [],
            extra={"llm": True, "voice": True},
            reply_prefix=prefix,
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("voice turn failed")
        return fail(tr.MSG_FAILED, type(exc).__name__)


def process_telegram_update(
    update: Dict[str, Any],
    invoke_chat: ChatInvoke,
    *,
    reset_session: Callable[[str], None] | None = None,
    compact_session: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    """Process one Telegram update dict; invoke_chat(message, session_id) -> {response: ...}."""
    message = update.get("message") or {}
    sender = (message.get("chat") or {}).get("id", "telegram")
    if not _chat_allowed(sender):
        _log.info("telegram update from disallowed chat %s ignored", sender)
        return {"ok": True, "skipped": "chat not allowed"}
    if "text" not in message:
        attachment = _voice_attachment(message)
        if attachment:
            return _voice_turn(message, attachment, invoke_chat)
        return {"ok": True, "skipped": "no text"}

    text = message["text"]
    chat_id = (message.get("chat") or {}).get("id", "telegram")
    session_id = f"telegram-{chat_id}"
    forwarded = any(
        message.get(k) for k in ("forward_origin", "forward_from", "forward_from_chat", "forward_date")
    )

    from services.chat_commands import try_chat_command

    cmd_reply = try_chat_command(
        text,
        session_id=session_id,
        on_reset=(lambda: reset_session(session_id)) if reset_session else None,
        on_compact=(lambda: compact_session(session_id)) if compact_session else None,
    )
    if cmd_reply:
        return _reply_direct(
            session_id=session_id,
            chat_id=chat_id,
            text=text,
            ai_content=cmd_reply,
            tools=[{"type": "direct", "tool": "chat_command"}],
            extra={"chat_command": True},
        )

    if not forwarded:
        # "nomeia N <nome>" / "ignora N" on the Monday briefing's unnamed-conversation items.
        try:
            from services.contact_names import try_name_reply

            named = try_name_reply(text, session_id)
        except Exception as exc:
            from services.soft_fail import soft_fail
            soft_fail("telegram_handler.name_reply", exc)
            named = None
        if named:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=named,
                tools=[{"type": "direct", "tool": "contact_name_reply"}],
                extra={"name_reply": True},
            )

    if direct_handlers_enabled():
        reviewed = try_direct_review(text, confirmed_via="telegram")
        if reviewed:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=reviewed,
                tools=[{"type": "direct", "tool": "commitment_review"}],
                extra={"review_direct": True},
            )

        direct = try_direct_schedule(text)
        if direct:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=direct,
                tools=[{"type": "direct", "tool": "schedule_event"}],
                extra={"scheduled_direct": True},
            )

        tasked = try_direct_task(text)
        if tasked:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=tasked,
                tools=[{"type": "direct", "tool": "create_task"}],
                extra={"task_direct": True},
            )

        emailed = try_direct_email(text)
        if emailed:
            return _reply_direct(
                session_id=session_id,
                chat_id=chat_id,
                text=text,
                ai_content=emailed,
                tools=[{"type": "direct", "tool": "summarize_inbox"}],
                extra={"email_direct": True},
            )

    try:
        result = (
            invoke_chat(text, session_id, forwarded=True)  # type: ignore[call-arg]
            if forwarded
            else invoke_chat(text, session_id)
        )
    except Exception as exc:
        detail = str(exc)
        ai_content = (
            "Não consegui processar sua mensagem agora. "
            f"Detalhe: {detail[:180]}"
        )
        return _reply_direct(
            session_id=session_id,
            chat_id=chat_id,
            text=text,
            ai_content=ai_content,
            tools=[{"type": "error", "detail": detail[:500]}],
            extra={"error": True},
        )

    try:
        from services.profile_updater import extract_profile_facts, merge_profile

        merge_profile(str(chat_id), extract_profile_facts(text))
    except Exception as exc:
        from services.soft_fail import soft_fail
        soft_fail("telegram_handler.process_telegram_update", exc)

    tools = result.get("tools") or []
    output_messages = result.get("output_messages") or []
    audit_payload = tools if tools else output_messages
    return _reply_direct(
        session_id=session_id,
        chat_id=chat_id,
        text=text,
        ai_content=result.get("response") or "",
        tools=audit_payload if isinstance(audit_payload, list) else [],
        extra={"llm": True},
    )
