"""Unit tests for Telegram handler (SCN-TG-01/02)."""

import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.telegram_handler import process_telegram_update  # noqa: E402


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
        return {"response": "Oi!"}

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
    test_processes_gemini_content_blocks()
    print("ok")
