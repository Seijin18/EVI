"""Unit tests for services/whatsapp_control.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.whatsapp_control import process_whatsapp_control_message  # noqa: E402


def _invoke(text, session_id):
    return {"response": f"LLM: {text}"}


def test_echo_skip():
    result = process_whatsapp_control_message(
        jid="5511@c.us",
        text="[EVI] hello",
        invoke_chat=_invoke,
    )
    assert result["skipped"] == "evi_echo"


def test_direct_review_path():
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


def test_direct_schedule_path():
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


def test_direct_task_path():
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


def test_llm_fallback():
    with patch("services.whatsapp_control.try_direct_review", return_value=None):
        with patch("services.whatsapp_control.try_direct_schedule", return_value=None):
            with patch("services.whatsapp_control.try_direct_task", return_value=None):
                with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
                    result = process_whatsapp_control_message(
                        jid="5511@c.us",
                        text="como está o tempo?",
                        invoke_chat=_invoke,
                    )
    assert "LLM:" in result["response"]
    assert result["ok"] is True


def test_empty_llm_reply_returns_hint():
    with patch("services.whatsapp_control.try_direct_review", return_value=None):
        with patch("services.whatsapp_control.try_direct_schedule", return_value=None):
            with patch("services.whatsapp_control.try_direct_task", return_value=None):
                with patch("services.whatsapp_control.send_whatsapp_text", return_value=True):
                    result = process_whatsapp_control_message(
                        jid="5511@c.us",
                        text="?",
                        invoke_chat=lambda t, s: {"response": ""},
                    )
    assert "Não obtive resposta" in result["response"] or "resposta" in result["response"].lower()


if __name__ == "__main__":
    test_echo_skip()
    test_direct_review_path()
    test_direct_schedule_path()
    test_direct_task_path()
    test_llm_fallback()
    test_empty_llm_reply_returns_hint()
    print("ok")
