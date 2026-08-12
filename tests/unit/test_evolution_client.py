"""SCN-WA-18 — the outbound WhatsApp path and the Evolution query helpers."""

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from messaging.evolution import EvolutionClient, reply_prefix  # noqa: E402
from services import send_result as sr  # noqa: E402
from services.evolution_client import (  # noqa: E402
    format_evi_whatsapp,
    is_evi_bot_message,
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(sr.time, "sleep", lambda _s: None)
    monkeypatch.setenv("EVOLUTION_SERVER_URL", "http://evolution-api:8080")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "evi")
    monkeypatch.setenv("EVOLUTION_API_KEY", "k")
    monkeypatch.delenv("EVI_SEND_RETRY_ATTEMPTS", raising=False)


class _Resp:
    def __init__(self, body="{}", status=200):
        self.status = status
        self._body = body

    def read(self):
        return self._body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen(monkeypatch, outcomes, target=sr):
    calls = {"n": 0, "reqs": []}

    def fake(req, timeout=None):
        i = calls["n"]
        calls["n"] += 1
        calls["reqs"].append(req)
        item = outcomes[min(i, len(outcomes) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(target.urllib.request, "urlopen", fake)
    return calls


# --- send_text --------------------------------------------------------------


def test_send_text_posts_to_the_instance(monkeypatch):
    calls = _urlopen(monkeypatch, [_Resp()])
    out = EvolutionClient().send_text("5511999@s.whatsapp.net", "oi")
    assert bool(out) is True
    req = calls["reqs"][0]
    assert "/message/sendText/evi" in req.full_url
    body = json.loads(req.data.decode())
    assert body["number"] == "5511999", "the JID suffix must be stripped"
    assert body["text"].startswith(reply_prefix())


def test_send_text_without_prefix(monkeypatch):
    calls = _urlopen(monkeypatch, [_Resp()])
    EvolutionClient().send_text("5511999@s.whatsapp.net", "oi", add_prefix=False)
    body = json.loads(calls["reqs"][0].data.decode())
    assert not body["text"].startswith(reply_prefix())


def test_send_text_carries_the_api_key(monkeypatch):
    calls = _urlopen(monkeypatch, [_Resp()])
    EvolutionClient().send_text("5511999@s.whatsapp.net", "oi")
    assert calls["reqs"][0].get_header("Apikey") == "k"


def test_send_text_retries_a_transport_blip(monkeypatch):
    calls = _urlopen(monkeypatch, [OSError("Network is unreachable"), _Resp()])
    out = EvolutionClient().send_text("5511999@s.whatsapp.net", "oi")
    assert bool(out) is True and calls["n"] == 2


def test_send_text_does_not_retry_a_4xx(monkeypatch):
    """A closed instance or bad key fails the same way next time."""
    calls = _urlopen(
        monkeypatch, [urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)]
    )
    out = EvolutionClient().send_text("5511999@s.whatsapp.net", "oi")
    assert bool(out) is False and out.reason == sr.HTTP_4XX and calls["n"] == 1


def test_send_text_reports_missing_config(monkeypatch):
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "")
    out = EvolutionClient().send_text("5511999@s.whatsapp.net", "oi")
    assert out.reason == sr.NOT_CONFIGURED
    assert "EVOLUTION_INSTANCE_NAME" in out.detail


def test_send_text_rejects_empty_body(monkeypatch):
    out = EvolutionClient().send_text("5511999@s.whatsapp.net", "   ")
    assert out.reason == sr.EMPTY_TEXT


def test_send_text_rejects_empty_jid(monkeypatch):
    out = EvolutionClient().send_text("", "oi")
    assert out.reason == sr.NOT_CONFIGURED


def test_send_text_truncates_long_bodies(monkeypatch):
    calls = _urlopen(monkeypatch, [_Resp()])
    EvolutionClient().send_text("5511999@s.whatsapp.net", "x" * 9000)
    body = json.loads(calls["reqs"][0].data.decode())
    assert len(body["text"]) <= 4000


# --- echo guard -------------------------------------------------------------


def test_bot_messages_are_recognised():
    """Without this the agent would answer its own replies in the control chat."""
    assert is_evi_bot_message("[EVI] já agendei") is True
    assert is_evi_bot_message("[evi]  minúsculo") is True
    assert is_evi_bot_message("oi, tudo bem?") is False


def test_format_reply_is_idempotent():
    once = format_evi_whatsapp("oi")
    assert format_evi_whatsapp(once) == once, "re-prefixing would stack [EVI][EVI]"


def test_format_reply_normalises_a_missing_space():
    assert format_evi_whatsapp("[EVI]colado").startswith(reply_prefix())


# --- query helpers ----------------------------------------------------------


def test_find_contacts_uses_the_configured_limit(monkeypatch):
    """The 300 default truncated a 2553-contact address book."""
    monkeypatch.setenv("EVI_EVOLUTION_CONTACTS_LIMIT", "1234")
    with patch(
        "messaging.evolution.urllib.request.urlopen",
        side_effect=lambda req, timeout=None: _Resp(json.dumps([{"remoteJid": "x"}])),
    ) as u:
        out = EvolutionClient().find_contacts()
        body = json.loads(u.call_args[0][0].data.decode())
    assert body["offset"] == 1234
    assert out == [{"remoteJid": "x"}]


def test_find_contacts_returns_none_without_instance(monkeypatch):
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "")
    assert EvolutionClient().find_contacts() is None


def test_find_messages_scopes_to_the_jid():
    with patch(
        "messaging.evolution.urllib.request.urlopen",
        side_effect=lambda req, timeout=None: _Resp("[]"),
    ) as u:
        EvolutionClient().find_messages("5511999@s.whatsapp.net", limit=7)
        body = json.loads(u.call_args[0][0].data.decode())
    assert body["where"]["key"]["remoteJid"] == "5511999@s.whatsapp.net"
    assert body["offset"] == 7


def test_post_json_swallows_transport_errors():
    with patch(
        "messaging.evolution.urllib.request.urlopen",
        side_effect=OSError("refused"),
    ):
        assert EvolutionClient().find_chats() is None
