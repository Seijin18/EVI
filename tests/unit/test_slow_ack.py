import time
from unittest.mock import patch

import pytest

from services import slow_ack
from services.turn_log import TurnCollector, end_turn, start_turn


@pytest.fixture
def sent():
    out = []
    with patch.object(slow_ack, "_send", lambda ch, sid, text: out.append((ch, sid, text))):
        yield out


def _run(c, tool, secs, rid):
    c.on_tool_start({"name": tool}, "", run_id=rid)
    time.sleep(secs)
    c.on_tool_end("ok", run_id=rid)


def test_off_by_default(sent, monkeypatch):
    monkeypatch.delenv("EVI_SLOW_ACK_SEC", raising=False)
    c = TurnCollector("telegram", session_id="telegram-1")
    _run(c, "summarize_inbox", 0.15, "a")
    assert sent == []


def test_slow_tool_one_ack(sent, monkeypatch):
    monkeypatch.setenv("EVI_SLOW_ACK_SEC", "0.05")
    c = TurnCollector("telegram", session_id="telegram-1")
    _run(c, "summarize_inbox", 0.25, "a")
    assert sent == [("telegram", "telegram-1", "⏳ fazendo… (lendo seus e-mails)")]


def test_fast_tool_no_ack(sent, monkeypatch):
    monkeypatch.setenv("EVI_SLOW_ACK_SEC", "0.2")
    c = TurnCollector("telegram", session_id="telegram-1")
    _run(c, "summarize_inbox", 0.01, "a")
    time.sleep(0.3)
    assert sent == []


def test_two_slow_tools_still_one(sent, monkeypatch):
    monkeypatch.setenv("EVI_SLOW_ACK_SEC", "0.05")
    c = TurnCollector("telegram", session_id="telegram-1")
    _run(c, "delete_emails_by_query", 0.2, "a")
    _run(c, "create_task", 0.2, "b")
    assert len(sent) == 1
    assert "apagando e-mails" in sent[0][2]


def test_api_and_test_turns_never(sent, monkeypatch):
    monkeypatch.setenv("EVI_SLOW_ACK_SEC", "0.05")
    _run(TurnCollector("api", session_id="x"), "summarize_inbox", 0.2, "a")
    _run(TurnCollector("telegram", is_test=True, session_id="telegram-1"), "x", 0.2, "b")
    c, token = start_turn("telegram", "test-1")
    _run(c, "x", 0.2, "c")
    end_turn(token)
    assert sent == []


def test_end_turn_cancels(sent, monkeypatch):
    monkeypatch.setenv("EVI_SLOW_ACK_SEC", "0.1")
    c, token = start_turn("telegram", "telegram-1")
    c.on_tool_start({"name": "x"}, "", run_id="a")
    end_turn(token)
    time.sleep(0.25)
    assert sent == []


def test_friendly_default():
    assert slow_ack.friendly_tool_name("whatever") == "trabalhando nisso"
    assert slow_ack.friendly_tool_name("schedule_event") == "agendando"


def test_routing_telegram_and_whatsapp(monkeypatch):
    with patch("services.telegram_notify.send_telegram_message") as tg, patch(
        "services.evolution_client.send_whatsapp_text"
    ) as wa:
        slow_ack._send("telegram", "telegram-42", "m")
        tg.assert_called_once_with("m", chat_id="42")
        slow_ack._send("whatsapp_control", "whatsapp-5511@s.whatsapp.net", "m")
        wa.assert_called_once_with("5511@s.whatsapp.net", "m", add_prefix=True)
        slow_ack._send("api", "x", "m")
        assert tg.call_count == 1 and wa.call_count == 1
