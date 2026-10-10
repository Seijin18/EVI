"""Unit tests for services/whatsapp_control.py."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.whatsapp_control import process_whatsapp_control_message  # noqa: E402

_DIRECT_ON = patch.dict(os.environ, {"EVI_DIRECT_HANDLERS": "true"}, clear=False)
_DIRECT_OFF = patch.dict(os.environ, {"EVI_DIRECT_HANDLERS": "false"}, clear=False)


def _invoke(text, session_id):
    return {"response": f"LLM: {text}", "tools": [{"kind": "call", "tool": "summarize_inbox"}]}


def test_echo_skip():
    with _DIRECT_OFF:
        result = process_whatsapp_control_message(
            jid="5511@c.us",
            text="[EVI] hello",
            invoke_chat=_invoke,
        )
    assert result["skipped"] == "evi_echo"


def test_direct_review_path_when_enabled():
    with _DIRECT_ON:
        with patch("services.whatsapp_control.try_direct_review", return_value="Pendentes: []") as mock_review:
            with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
                result = process_whatsapp_control_message(
                    jid="5511@c.us",
                    text="listar compromissos pendentes",
                    invoke_chat=_invoke,
                )
    mock_review.assert_called_once()
    assert result["review_direct"] is True
    assert result["whatsapp_sent"] is True


def test_direct_schedule_path_when_enabled():
    with _DIRECT_ON:
        with patch("services.whatsapp_control.try_direct_review", return_value=None):
            with patch("services.whatsapp_control.try_direct_schedule", return_value="Agendado!") as mock_sched:
                with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
                    result = process_whatsapp_control_message(
                        jid="5511@c.us",
                        text="agende almoço amanhã 12h",
                        invoke_chat=_invoke,
                    )
    mock_sched.assert_called_once()
    assert result["scheduled_direct"] is True


def test_direct_task_path_when_enabled():
    with _DIRECT_ON:
        with patch("services.whatsapp_control.try_direct_review", return_value=None):
            with patch("services.whatsapp_control.try_direct_schedule", return_value=None):
                with patch("services.whatsapp_control.try_direct_task", return_value="Tarefa criada!") as mock_task:
                    with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
                        result = process_whatsapp_control_message(
                            jid="5511@c.us",
                            text="criar tarefa teste",
                            invoke_chat=_invoke,
                        )
    mock_task.assert_called_once()
    assert result["task_direct"] is True


def test_llm_first_when_direct_handlers_off():
    with _DIRECT_OFF:
        with patch("services.whatsapp_control.try_direct_review") as mock_review:
            with patch("services.whatsapp_control.try_direct_schedule") as mock_sched:
                with patch("services.whatsapp_control.try_direct_task") as mock_task:
                    with patch("services.whatsapp_control.try_direct_email") as mock_email:
                        with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
                            result = process_whatsapp_control_message(
                                jid="5511@c.us",
                                text="listar compromissos pendentes",
                                invoke_chat=_invoke,
                            )
    mock_review.assert_not_called()
    mock_sched.assert_not_called()
    mock_task.assert_not_called()
    mock_email.assert_not_called()
    assert result.get("llm") is True
    assert "LLM:" in result["response"]


def test_llm_first_inbox_phrase_when_direct_handlers_off():
    with _DIRECT_OFF:
        with patch("services.whatsapp_control.try_direct_email") as mock_email:
            with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
                result = process_whatsapp_control_message(
                    jid="5511@c.us",
                    text="Revise meus emails",
                    invoke_chat=_invoke,
                )
    mock_email.assert_not_called()
    assert result.get("llm") is True
    assert result.get("tools")


def test_llm_fallback():
    with _DIRECT_OFF:
        with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
            result = process_whatsapp_control_message(
                jid="5511@c.us",
                text="como está o tempo?",
                invoke_chat=_invoke,
            )
    assert "LLM:" in result["response"]
    assert result["ok"] is True


def test_llm_gemini_content_blocks():
    gemini_response = [
        {"type": "text", "text": "Está ensolarado.", "extras": {"signature": "x"}},
    ]

    def invoke(_text, _session):
        return {"response": gemini_response}

    with _DIRECT_OFF, patch.dict(os.environ, {"EVI_LLM_PROVIDER": "gemini"}):
        with patch("services.whatsapp_control.send_whatsapp_text", return_value=True) as send:
            result = process_whatsapp_control_message(
                jid="5511@c.us",
                text="tempo?",
                invoke_chat=invoke,
            )
    assert result["ok"] is True
    send.assert_called_once()
    assert send.call_args.args[1] == "Está ensolarado."


def test_empty_llm_reply_returns_hint():
    with _DIRECT_OFF:
        with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
            result = process_whatsapp_control_message(
                jid="5511@c.us",
                text="?",
                invoke_chat=lambda t, s: {"response": ""},
            )
    assert "Não obtive resposta" in result["response"] or "resposta" in result["response"].lower()


if __name__ == "__main__":
    test_echo_skip()
    test_direct_review_path_when_enabled()
    test_direct_schedule_path_when_enabled()
    test_direct_task_path_when_enabled()
    test_llm_first_when_direct_handlers_off()
    test_llm_first_inbox_phrase_when_direct_handlers_off()
    test_llm_fallback()
    test_llm_gemini_content_blocks()
    test_empty_llm_reply_returns_hint()
    print("ok")


# --- voice notes (evi-voice-input) -------------------------------------------

from services.transcribe import MSG_DISABLED, TranscriptionResult  # noqa: E402

_KEY = {"id": "AUD1", "remoteJid": "5511@s.whatsapp.net", "fromMe": False}


def _voice(invoke=None, **kw):
    calls = []

    def default_invoke(text, session_id, input_kind="text"):
        calls.append((text, input_kind))
        return {"response": "Amanhã você tem 2 compromissos.", "tools": []}

    with _DIRECT_OFF:
        result = process_whatsapp_control_message(
            jid="5511@s.whatsapp.net",
            text="",
            invoke_chat=invoke or default_invoke,
            kind="audio",
            audio_seconds=kw.pop("audio_seconds", 5),
            media_key=_KEY,
            **kw,
        )
    return result, calls


def test_voice_note_is_transcribed_and_echoed():  # SCN-VOICE-02
    sent = []
    with patch.dict(os.environ, {"EVI_VOICE_ENABLED": "true"}), patch(
        "services.whatsapp_control.get_whatsapp_media", return_value=(b"ogg", "audio/ogg")
    ) as media, patch(
        "services.transcribe.transcribe",
        return_value=TranscriptionResult(ok=True, text="quais meus compromissos de amanhã?"),
    ), patch(
        "services.whatsapp_control.send_whatsapp_text",
        side_effect=lambda jid, text, **k: sent.append(text) or True,
    ):
        result, calls = _voice()
    media.assert_called_once_with(_KEY)
    assert calls == [("quais meus compromissos de amanhã?", "voice")]
    assert sent[0].startswith("🎙️ Entendi: quais meus compromissos de amanhã?\n\n")
    assert "compromissos" in sent[0]
    assert result["whatsapp_sent"]


def test_voice_echo_is_truncated():
    sent = []
    long = "palavra " * 60
    with patch.dict(os.environ, {"EVI_VOICE_ENABLED": "true"}), patch(
        "services.whatsapp_control.get_whatsapp_media", return_value=(b"ogg", "audio/ogg")
    ), patch(
        "services.transcribe.transcribe", return_value=TranscriptionResult(ok=True, text=long)
    ), patch(
        "services.whatsapp_control.send_whatsapp_text",
        side_effect=lambda jid, text, **k: sent.append(text) or True,
    ):
        _voice()
    echo_line = sent[0].split("\n\n")[0]
    assert len(echo_line) <= len("🎙️ Entendi: ") + 200


def test_voice_disabled_replies_without_download():
    sent = []
    with patch.dict(os.environ, {"EVI_VOICE_ENABLED": "false"}), patch(
        "services.whatsapp_control.get_whatsapp_media"
    ) as media, patch(
        "services.whatsapp_control.send_whatsapp_text",
        side_effect=lambda jid, text, **k: sent.append(text) or True,
    ):
        result, calls = _voice()
    media.assert_not_called()
    assert sent == [MSG_DISABLED]
    assert not calls and result["voice_error"] == "disabled"


def test_voice_too_long_checked_before_download():
    sent = []
    with patch.dict(os.environ, {"EVI_VOICE_ENABLED": "true", "EVI_VOICE_MAX_SECONDS": "60"}), patch(
        "services.whatsapp_control.get_whatsapp_media"
    ) as media, patch(
        "services.whatsapp_control.send_whatsapp_text",
        side_effect=lambda jid, text, **k: sent.append(text) or True,
    ):
        result, calls = _voice(audio_seconds=120)
    media.assert_not_called()
    assert sent and "min" in sent[0] and not calls


def test_voice_download_failure_is_visible():
    sent = []
    with patch.dict(os.environ, {"EVI_VOICE_ENABLED": "true"}), patch(
        "services.whatsapp_control.get_whatsapp_media", return_value=None
    ), patch(
        "services.whatsapp_control.send_whatsapp_text",
        side_effect=lambda jid, text, **k: sent.append(text) or True,
    ):
        result, calls = _voice()
    assert sent and not calls and result["voice_error"] == "download_failed"


def test_voice_transcription_failure_sends_user_message():
    sent = []
    with patch.dict(os.environ, {"EVI_VOICE_ENABLED": "true"}), patch(
        "services.whatsapp_control.get_whatsapp_media", return_value=(b"x", "audio/ogg")
    ), patch(
        "services.transcribe.transcribe",
        return_value=TranscriptionResult(ok=False, reason="empty"),
    ), patch(
        "services.whatsapp_control.send_whatsapp_text",
        side_effect=lambda jid, text, **k: sent.append(text) or True,
    ):
        result, calls = _voice()
    assert sent == ["Não consegui entender o áudio, pode repetir?"] and not calls


def test_third_party_audio_never_reaches_media_or_control(monkeypatch):  # SCN-VOICE-05
    """main routes only control JIDs to the control handler; others never download."""
    from fastapi.testclient import TestClient

    import main

    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "5511@s.whatsapp.net")
    monkeypatch.setenv("EVI_LOG_DIR", str(Path(os.environ.get("TMPDIR", "/tmp")) / "evi-voice-test"))
    body = {
        "event": "messages.upsert",
        "data": {
            "key": {"id": "AUD9", "remoteJid": "5599@s.whatsapp.net", "fromMe": False},
            "messageTimestamp": 1767225600,
            "message": {"audioMessage": {"mimetype": "audio/ogg", "seconds": 5}},
        },
    }
    with patch("services.whatsapp_control.get_whatsapp_media") as media, patch(
        "services.whatsapp_control.process_whatsapp_control_message"
    ) as ctl, patch("services.whatsapp_control.send_whatsapp_text") as send:
        resp = TestClient(main.app).post("/webhooks/evolution", json=body)
    assert resp.status_code in (200, 202)
    media.assert_not_called()
    ctl.assert_not_called()
    send.assert_not_called()
