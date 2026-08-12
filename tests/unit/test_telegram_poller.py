"""SCN-TG-06 — the polling path, which is how this deployment actually runs.

`TELEGRAM_MODE=polling` is the production configuration here, and the module had
no tests at all. The behaviours that matter are the ones that keep the loop alive
and the offset advancing, because a regression there silently stops the bot.
"""

import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services import telegram_poller as tp  # noqa: E402


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(tp.time, "sleep", lambda _s: None)
    tp._stop.clear()
    yield
    tp._stop.set()


def _urlopen(monkeypatch, payloads):
    """Feed successive _api_get responses; an Exception instance raises."""
    calls = {"n": 0, "urls": []}

    class _Resp:
        def __init__(self, body):
            self._body = body

        def read(self):
            import json

            return json.dumps(self._body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        i = calls["n"]
        calls["n"] += 1
        calls["urls"].append(getattr(req, "full_url", str(req)))
        item = payloads[min(i, len(payloads) - 1)]
        if isinstance(item, Exception):
            raise item
        return _Resp(item)

    monkeypatch.setattr(tp.urllib.request, "urlopen", fake)
    return calls


# --- _api_get ---------------------------------------------------------------


def test_api_get_builds_the_bot_url(monkeypatch):
    calls = _urlopen(monkeypatch, [{"ok": True, "result": []}])
    tp._api_get("TOK", "getUpdates", {"offset": 5})
    url = calls["urls"][0]
    assert "/botTOK/getUpdates" in url
    assert "offset=5" in url


def test_api_get_raises_when_telegram_reports_not_ok(monkeypatch):
    _urlopen(monkeypatch, [{"ok": False, "description": "Unauthorized"}])
    with pytest.raises(RuntimeError, match="Unauthorized"):
        tp._api_get("TOK", "getMe")


def test_api_get_omits_none_params(monkeypatch):
    calls = _urlopen(monkeypatch, [{"ok": True, "result": []}])
    tp._api_get("TOK", "getUpdates", {"offset": 1, "nope": None})
    assert "nope" not in calls["urls"][0]


# --- delete_webhook ---------------------------------------------------------


def test_delete_webhook_swallows_transport_errors(monkeypatch):
    """Called before the loop starts; raising here would kill the thread."""
    _urlopen(monkeypatch, [urllib.error.URLError("boom")])
    assert tp.delete_webhook("TOK") is False


def test_delete_webhook_ok(monkeypatch):
    _urlopen(monkeypatch, [{"ok": True, "result": True}])
    assert tp.delete_webhook("TOK") is True


# --- fetch_updates ----------------------------------------------------------


def test_fetch_updates_returns_result_list(monkeypatch):
    _urlopen(monkeypatch, [{"ok": True, "result": [{"update_id": 1}]}])
    assert tp.fetch_updates("TOK") == [{"update_id": 1}]


def test_fetch_updates_tolerates_missing_result(monkeypatch):
    _urlopen(monkeypatch, [{"ok": True}])
    assert tp.fetch_updates("TOK") == []


# --- the loop ---------------------------------------------------------------


def _run_loop_once(monkeypatch, updates, handler=None):
    """Run _poll_loop for a single iteration then stop it."""
    seen = []

    def _process(update, invoke, **kw):
        seen.append(update)
        tp._stop.set()  # one pass only
        if handler:
            return handler(update)
        return {"session_id": "s", "telegram_sent": True}

    monkeypatch.setattr(tp, "delete_webhook", lambda *a, **k: True)
    monkeypatch.setattr(tp, "fetch_updates", lambda *a, **k: updates)
    monkeypatch.setattr(tp, "process_telegram_update", _process)
    tp._poll_loop("TOK", MagicMock())
    return seen


def test_loop_dispatches_each_update(monkeypatch):
    seen = _run_loop_once(monkeypatch, [{"update_id": 10, "message": {"text": "oi"}}])
    assert seen and seen[0]["update_id"] == 10


def test_loop_survives_a_handler_exception(monkeypatch):
    """One bad update must not take the poller down."""

    def _boom(_update):
        raise ValueError("handler exploded")

    seen = _run_loop_once(monkeypatch, [{"update_id": 1}], handler=_boom)
    assert seen  # it was attempted, and the loop exited normally rather than raising


def test_loop_survives_a_fetch_exception(monkeypatch):
    """The 'Network is unreachable' case seen in production."""
    calls = {"n": 0}

    def _fetch(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("Network is unreachable")
        tp._stop.set()
        return []

    monkeypatch.setattr(tp, "delete_webhook", lambda *a, **k: True)
    monkeypatch.setattr(tp, "fetch_updates", _fetch)
    tp._poll_loop("TOK", MagicMock())
    assert calls["n"] == 2, "loop must retry after a transport failure, not exit"


def test_offset_advances_past_processed_updates(monkeypatch):
    """A stale offset replays updates forever — the classic polling bug."""
    offsets = []

    def _fetch(_token, offset=0, timeout=30):
        offsets.append(offset)
        if len(offsets) >= 2:
            tp._stop.set()
            return []
        return [{"update_id": 41}, {"update_id": 42}]

    monkeypatch.setattr(tp, "delete_webhook", lambda *a, **k: True)
    monkeypatch.setattr(tp, "fetch_updates", _fetch)
    monkeypatch.setattr(
        tp, "process_telegram_update", lambda *a, **k: {"session_id": "s"}
    )
    tp._poll_loop("TOK", MagicMock())
    assert offsets == [0, 43], "offset must be highest update_id + 1"


def test_loop_deletes_the_webhook_before_polling(monkeypatch):
    """Polling and a registered webhook are mutually exclusive on Telegram."""
    called = []
    monkeypatch.setattr(tp, "delete_webhook", lambda *a, **k: called.append(1) or True)
    monkeypatch.setattr(tp, "fetch_updates", lambda *a, **k: tp._stop.set() or [])
    tp._poll_loop("TOK", MagicMock())
    assert called


# --- start/stop -------------------------------------------------------------


def test_start_poller_needs_a_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with patch.object(tp.threading, "Thread") as thread:
        tp.start_poller(MagicMock())
    thread.assert_not_called()


def test_start_poller_spawns_a_daemon_thread(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOK")
    tp._thread = None
    with patch.object(tp.threading, "Thread") as thread:
        tp.start_poller(MagicMock())
    thread.assert_called_once()
    assert thread.call_args.kwargs.get("daemon") is True
