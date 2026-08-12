"""SCN-SEND-01/02 — the Telegram sender retries transport errors and reports why."""

import sys
import urllib.error
from pathlib import Path

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services import send_result as sr  # noqa: E402
from services.telegram_notify import send_telegram_message  # noqa: E402


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(sr.time, "sleep", lambda _s: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.delenv("EVI_SEND_RETRY_ATTEMPTS", raising=False)


def _urlopen(monkeypatch, outcomes):
    calls = {"n": 0}

    def fake(_req, timeout=None):
        i = calls["n"]
        calls["n"] += 1
        out = outcomes[min(i, len(outcomes) - 1)]
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(sr.urllib.request, "urlopen", fake)
    return calls


def test_delivers_on_first_try(monkeypatch):
    _urlopen(monkeypatch, [_Resp()])
    out = send_telegram_message("oi")
    assert bool(out) is True
    assert out.reason == ""


def test_survives_a_transient_blip(monkeypatch):
    """The exact failure that made evi-telegram-verify.sh drop a computed reply."""
    calls = _urlopen(monkeypatch, [OSError("Network is unreachable"), _Resp()])
    out = send_telegram_message("oi")
    assert bool(out) is True
    assert out.attempts == 2 and calls["n"] == 2


def test_reports_transport_failure(monkeypatch):
    _urlopen(monkeypatch, [OSError("Network is unreachable")])
    out = send_telegram_message("oi")
    assert bool(out) is False
    assert out.reason == sr.TRANSPORT


def test_bad_token_is_not_retried(monkeypatch):
    calls = _urlopen(
        monkeypatch, [urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)]
    )
    out = send_telegram_message("oi")
    assert out.reason == sr.HTTP_4XX
    assert calls["n"] == 1


def test_missing_token_is_not_configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    out = send_telegram_message("oi")
    assert bool(out) is False
    assert out.reason == sr.NOT_CONFIGURED
    assert "TELEGRAM_BOT_TOKEN" in out.detail


def test_missing_chat_id_is_not_configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    out = send_telegram_message("oi")
    assert out.reason == sr.NOT_CONFIGURED


def test_empty_text_is_reported(monkeypatch):
    _urlopen(monkeypatch, [_Resp()])
    out = send_telegram_message("   ")
    assert bool(out) is False
    assert out.reason == sr.EMPTY_TEXT


def test_handler_surfaces_send_error(monkeypatch):
    """telegram_sent stays a plain bool; the reason rides alongside it."""
    from services import telegram_handler as th

    _urlopen(monkeypatch, [OSError("Network is unreachable")])
    monkeypatch.setattr(th, "_persist_turn", lambda *a, **k: None)
    monkeypatch.setattr(th, "log_telegram_turn", lambda *a, **k: None)

    out = th._reply_direct(
        session_id="s", chat_id=1, text="oi", ai_content="resposta", tools=[]
    )
    assert out["telegram_sent"] is False
    assert isinstance(out["telegram_sent"], bool)
    assert out["send_error"] == sr.TRANSPORT


def test_handler_omits_send_error_on_success(monkeypatch):
    from services import telegram_handler as th

    _urlopen(monkeypatch, [_Resp()])
    monkeypatch.setattr(th, "_persist_turn", lambda *a, **k: None)
    monkeypatch.setattr(th, "log_telegram_turn", lambda *a, **k: None)

    out = th._reply_direct(
        session_id="s", chat_id=1, text="oi", ai_content="resposta", tools=[]
    )
    assert out["telegram_sent"] is True
    assert "send_error" not in out
