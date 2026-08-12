"""SCN-SEND-01 — bounded retry for transport errors, never for 4xx."""

import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services import send_result as sr  # noqa: E402


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(sr.time, "sleep", lambda _s: None)
    monkeypatch.delenv("EVI_SEND_RETRY_ATTEMPTS", raising=False)
    monkeypatch.delenv("EVI_SEND_RETRY_BACKOFF_SEC", raising=False)


class _Resp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _req():
    return urllib.request.Request("https://example.invalid/x", data=b"{}", method="POST")


def _patch_urlopen(monkeypatch, side_effects):
    calls = {"n": 0}

    def fake(_req, timeout=None):
        i = calls["n"]
        calls["n"] += 1
        outcome = side_effects[min(i, len(side_effects) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(sr.urllib.request, "urlopen", fake)
    return calls


def test_result_is_truthy_only_when_sent():
    assert bool(sr.SendResult.ok()) is True
    assert bool(sr.SendResult.fail(sr.TRANSPORT)) is False
    # Existing call sites do `if send_...(...)` — truthiness must carry them.
    assert (sr.SendResult.ok() and "delivered") == "delivered"


def test_first_attempt_success(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [_Resp(200)])
    out = sr.post_with_retry(_req(), timeout=5, context="t")
    assert out.sent is True and out.attempts == 1 and calls["n"] == 1


def test_transport_error_then_success(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [OSError("Network is unreachable"), _Resp(200)])
    out = sr.post_with_retry(_req(), timeout=5, context="t")
    assert out.sent is True
    assert out.attempts == 2
    assert calls["n"] == 2


def test_transport_error_exhausts_budget(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [OSError("Network is unreachable")])
    out = sr.post_with_retry(_req(), timeout=5, context="t")
    assert out.sent is False
    assert out.reason == sr.TRANSPORT
    assert out.attempts == 2
    assert calls["n"] == 2
    assert "OSError" in out.detail


def test_4xx_is_not_retried(monkeypatch):
    """A bad token or chat_id fails identically next time — retrying only delays it."""
    err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
    calls = _patch_urlopen(monkeypatch, [err])
    out = sr.post_with_retry(_req(), timeout=5, context="t")
    assert out.sent is False
    assert out.reason == sr.HTTP_4XX
    assert out.attempts == 1
    assert calls["n"] == 1


def test_5xx_is_retried(monkeypatch):
    err = urllib.error.HTTPError("u", 502, "Bad Gateway", {}, None)
    calls = _patch_urlopen(monkeypatch, [err, _Resp(200)])
    out = sr.post_with_retry(_req(), timeout=5, context="t")
    assert out.sent is True and calls["n"] == 2


def test_attempt_budget_is_configurable(monkeypatch):
    monkeypatch.setenv("EVI_SEND_RETRY_ATTEMPTS", "4")
    calls = _patch_urlopen(monkeypatch, [OSError("boom")])
    out = sr.post_with_retry(_req(), timeout=5, context="t")
    assert out.attempts == 4 and calls["n"] == 4


def test_garbage_budget_falls_back(monkeypatch):
    monkeypatch.setenv("EVI_SEND_RETRY_ATTEMPTS", "not-a-number")
    monkeypatch.setenv("EVI_SEND_RETRY_BACKOFF_SEC", "nope")
    calls = _patch_urlopen(monkeypatch, [OSError("boom")])
    out = sr.post_with_retry(_req(), timeout=5, context="t")
    assert out.attempts == 2 and calls["n"] == 2


def test_one_log_line_per_dropped_message(monkeypatch, caplog):
    _patch_urlopen(monkeypatch, [OSError("Network is unreachable")])
    with caplog.at_level("WARNING"):
        sr.post_with_retry(_req(), timeout=5, context="telegram_notify.send")
    lines = [r for r in caplog.records if "soft-fail" in r.getMessage()]
    assert len(lines) == 1, "one dropped message must not produce one line per attempt"
    msg = lines[0].getMessage()
    assert "telegram_notify.send" in msg
    assert "reason=transport" in msg and "attempts=2" in msg


def test_success_logs_nothing(monkeypatch, caplog):
    _patch_urlopen(monkeypatch, [_Resp(200)])
    with caplog.at_level("WARNING"):
        sr.post_with_retry(_req(), timeout=5, context="t")
    assert not [r for r in caplog.records if "soft-fail" in r.getMessage()]
