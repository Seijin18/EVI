"""Unit tests for Telegram handler (SCN-TG-01/02)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.telegram_handler import process_telegram_update  # noqa: E402

_DIRECT_OFF = patch.dict(os.environ, {"EVI_DIRECT_HANDLERS": "false"}, clear=False)
_DIRECT_ON = patch.dict(os.environ, {"EVI_DIRECT_HANDLERS": "true"}, clear=False)


def test_skips_non_text():
    out = process_telegram_update({"message": {"chat": {"id": 1}}}, lambda m, s: {})
    assert out["skipped"] == "no text"


def test_processes_text_and_sends():
    update = {
        "message": {
            "text": "olá",
            "chat": {"id": 933619568, "type": "private"},
        }
    }

    def fake_chat(msg, session_id):
        assert msg == "olá"
        assert session_id == "telegram-933619568"
        return {"response": "Oi!", "tools": []}

    with _DIRECT_OFF:
        with (
            patch("services.telegram_handler.send_telegram_message", return_value=True) as send,
            patch("services.telegram_handler._persist_turn") as persist,
            patch("services.telegram_handler.log_telegram_turn") as audit,
        ):
            out = process_telegram_update(update, fake_chat)
    assert out["telegram_sent"] is True
    assert out["response"] == "Oi!"
    assert out.get("llm") is True
    send.assert_called_once()
    persist.assert_called_once_with("telegram-933619568", "olá", "Oi!")
    audit.assert_called_once()


def test_llm_first_inbox_when_direct_handlers_off():
    update = {
        "message": {
            "text": "Revise meus emails",
            "chat": {"id": 933619568, "type": "private"},
        }
    }
    invoked = []

    def fake_chat(msg, session_id):
        invoked.append((msg, session_id))
        return {
            "response": "3 emails recentes.",
            "tools": [{"kind": "call", "tool": "summarize_inbox"}],
        }

    with _DIRECT_OFF:
        with patch("services.telegram_handler.try_direct_email") as mock_email:
            with patch("services.telegram_handler.try_direct_review") as mock_review:
                with (
                    patch("services.telegram_handler.send_telegram_message", return_value=True),
                    patch("services.telegram_handler._persist_turn"),
                    patch("services.telegram_handler.log_telegram_turn"),
                ):
                    out = process_telegram_update(update, fake_chat)
    mock_email.assert_not_called()
    mock_review.assert_not_called()
    assert invoked == [("Revise meus emails", "telegram-933619568")]
    assert out.get("llm") is True
    assert out["response"] == "3 emails recentes."


def test_direct_email_when_handlers_enabled():
    update = {
        "message": {
            "text": "Revise meus emails",
            "chat": {"id": 933619568, "type": "private"},
        }
    }

    with _DIRECT_ON:
        with patch("services.telegram_handler.try_direct_review", return_value=None):
            with patch("services.telegram_handler.try_direct_schedule", return_value=None):
                with patch("services.telegram_handler.try_direct_task", return_value=None):
                    with patch(
                        "services.telegram_handler.try_direct_email",
                        return_value="Inbox summary",
                    ) as mock_email:
                        with (
                            patch("services.telegram_handler.send_telegram_message", return_value=True),
                            patch("services.telegram_handler._persist_turn"),
                            patch("services.telegram_handler.log_telegram_turn"),
                        ):
                            out = process_telegram_update(update, lambda m, s: {})
    mock_email.assert_called_once()
    assert out.get("email_direct") is True


def test_processes_gemini_content_blocks():
    update = {
        "message": {
            "text": "oi",
            "chat": {"id": 933619568, "type": "private"},
        }
    }
    gemini_response = [
        {"type": "text", "text": "Olá! Como posso ajudar?", "extras": {"signature": "x"}},
    ]

    def fake_chat(msg, session_id):
        return {"response": gemini_response}

    with _DIRECT_OFF, patch.dict(os.environ, {"EVI_LLM_PROVIDER": "gemini"}):
        with (
            patch("services.telegram_handler.send_telegram_message", return_value=True) as send,
            patch("services.telegram_handler._persist_turn"),
            patch("services.telegram_handler.log_telegram_turn"),
        ):
            out = process_telegram_update(update, fake_chat)
    assert out["telegram_sent"] is True
    assert out["response"] == "Olá! Como posso ajudar?"
    send.assert_called_once_with("Olá! Como posso ajudar?", chat_id=933619568)


if __name__ == "__main__":
    test_skips_non_text()
    test_processes_text_and_sends()
    test_llm_first_inbox_when_direct_handlers_off()
    test_direct_email_when_handlers_enabled()
    test_processes_gemini_content_blocks()
    print("ok")


# --- voice (evi-voice-input SCN-VOICE-01/03) ---------------------------------

import pytest  # noqa: E402

from services import transcribe as _tr  # noqa: E402

_VOICE = {"message": {"chat": {"id": 7}, "voice": {"file_id": "F1", "duration": 5, "file_size": 1000}}}


@pytest.fixture
def voice_env(monkeypatch):
    monkeypatch.setenv("EVI_VOICE_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET:TOKEN")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with (
        patch("services.telegram_handler.send_telegram_message", return_value=True) as send,
        patch("services.telegram_handler._persist_turn"),
        patch("services.telegram_handler.log_telegram_turn"),
    ):
        yield send


def test_voice_disabled_replies_without_download(voice_env, monkeypatch):
    monkeypatch.setenv("EVI_VOICE_ENABLED", "false")
    with patch("services.telegram_poller.download_file") as dl:
        out = process_telegram_update(_VOICE, lambda m, s, **k: {})
    dl.assert_not_called()
    voice_env.assert_called_once()
    assert voice_env.call_args.args[0] == _tr.MSG_DISABLED
    assert out["telegram_sent"] is True


def test_voice_too_long_no_download_no_transcribe(voice_env, monkeypatch):
    monkeypatch.setenv("EVI_VOICE_MAX_SECONDS", "300")
    update = {"message": {"chat": {"id": 7}, "voice": {"file_id": "F", "duration": 600}}}
    with (
        patch("services.telegram_poller.download_file") as dl,
        patch("services.transcribe.transcribe") as tx,
    ):
        process_telegram_update(update, lambda m, s, **k: {})
    dl.assert_not_called()
    tx.assert_not_called()
    assert "passa de" in voice_env.call_args.args[0]


def test_voice_ok_invokes_chat_with_voice_kind_and_echo(voice_env):
    seen = {}

    def chat(msg, sid, input_kind="text"):
        seen.update(msg=msg, sid=sid, kind=input_kind)
        return {"response": "Feito.", "tools": []}

    with (
        patch("services.telegram_poller.get_file_path", return_value="voice/a.oga"),
        patch("services.telegram_poller.download_file", return_value=b"OGG"),
        patch(
            "services.transcribe.transcribe",
            return_value=_tr.TranscriptionResult(True, "marca dentista"),
        ) as tx,
    ):
        out = process_telegram_update(_VOICE, chat)
    assert seen == {"msg": "marca dentista", "sid": "telegram-7", "kind": "voice"}
    assert tx.call_args.args[1] == "audio/ogg"
    sent = voice_env.call_args.args[0]
    assert sent.startswith("🎙️ Entendi: marca dentista\n\n")
    assert sent.endswith("Feito.")
    assert out["response"] == sent


def test_voice_echo_truncated_to_200(voice_env):
    with (
        patch("services.telegram_poller.get_file_path", return_value="p"),
        patch("services.telegram_poller.download_file", return_value=b"x"),
        patch("services.transcribe.transcribe", return_value=_tr.TranscriptionResult(True, "a" * 500)),
    ):
        process_telegram_update(_VOICE, lambda m, s, input_kind="text": {"response": "ok"})
    first = voice_env.call_args.args[0].split("\n\n")[0]
    assert len(first) <= len("🎙️ Entendi: ") + 201


def test_voice_download_failure_visible_and_token_not_leaked(voice_env, caplog):
    with patch(
        "services.telegram_poller.get_file_path",
        side_effect=RuntimeError("getFile failed: boom <token>"),
    ):
        out = process_telegram_update(_VOICE, lambda m, s, **k: {})
    assert voice_env.call_args.args[0] == _tr.MSG_FAILED
    assert "SECRET:TOKEN" not in str(out) and "SECRET:TOKEN" not in caplog.text


def test_voice_transcription_failure_uses_user_message(voice_env):
    with (
        patch("services.telegram_poller.get_file_path", return_value="p"),
        patch("services.telegram_poller.download_file", return_value=b"x"),
        patch(
            "services.transcribe.transcribe",
            return_value=_tr.TranscriptionResult(False, "", _tr.REASON_EMPTY),
        ),
    ):
        process_telegram_update(_VOICE, lambda m, s, **k: {})
    assert voice_env.call_args.args[0] == _tr.MSG_EMPTY


def test_voice_audio_uses_own_mime_and_other_chat_skipped(voice_env, monkeypatch):
    update = {"message": {"chat": {"id": 7}, "audio": {"file_id": "A", "mime_type": "audio/mpeg"}}}
    with (
        patch("services.telegram_poller.get_file_path", return_value="p"),
        patch("services.telegram_poller.download_file", return_value=b"x"),
        patch("services.transcribe.transcribe", return_value=_tr.TranscriptionResult(True, "oi")) as tx,
    ):
        process_telegram_update(update, lambda m, s, input_kind="text": {"response": "ok"})
        assert tx.call_args.args[1] == "audio/mpeg"
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
        out = process_telegram_update(update, lambda m, s, input_kind="text": {})
    assert out["skipped"] == "chat not allowed"
