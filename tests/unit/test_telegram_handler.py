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

    with _DIRECT_OFF:
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
