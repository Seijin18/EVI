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

    with _DIRECT_OFF:
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
