"""SCN-REM-01 — in-process reminder loop (daemon thread, tick, flag, soft_fail)."""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services import reminder_loop  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "true")
    monkeypatch.delenv("EVI_REMINDERS_TICK_SEC", raising=False)
    reminder_loop.stop_loop()
    yield
    reminder_loop.stop_loop()


def _wait(pred, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_flag_off_no_thread(monkeypatch):
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "false")
    assert reminder_loop.start_loop() is False
    assert reminder_loop._thread is None


def test_no_database_url_no_thread(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    assert reminder_loop.start_loop() is False
    assert reminder_loop._thread is None


def test_first_tick_immediate_and_start_idempotent():
    calls = threading.Event()
    with patch("services.reminders.fire_due", side_effect=lambda: calls.set()) as fd:
        assert reminder_loop.start_loop() is True
        assert calls.wait(2)  # long tick (30s): first tick must not wait
        t = reminder_loop._thread
        assert t.name == "reminder-loop" and t.daemon
        assert reminder_loop.start_loop() is True
        assert reminder_loop._thread is t
        assert fd.call_count == 1


def test_exception_in_tick_does_not_kill_loop(monkeypatch):
    monkeypatch.setattr(reminder_loop, "MIN_TICK_SEC", 0.01)
    monkeypatch.setenv("EVI_REMINDERS_TICK_SEC", "0.01")
    fd = MagicMock(side_effect=RuntimeError("boom"))
    with patch("services.reminders.fire_due", fd), patch.object(reminder_loop, "soft_fail") as sf:
        assert reminder_loop.start_loop()
        assert _wait(lambda: fd.call_count >= 3)
        assert reminder_loop._thread.is_alive()
        assert sf.called


def test_stop_joins_quickly_with_long_tick():
    with patch("services.reminders.fire_due"):
        reminder_loop.start_loop()
        t = reminder_loop._thread
        t0 = time.time()
        reminder_loop.stop_loop()
        assert time.time() - t0 < 1.0
        assert not t.is_alive()
        assert reminder_loop._thread is None


def test_tick_interval_default_and_min(monkeypatch):
    assert reminder_loop._tick_interval() == 30
    monkeypatch.setenv("EVI_REMINDERS_TICK_SEC", "1")
    assert reminder_loop._tick_interval() == 5
    monkeypatch.setenv("EVI_REMINDERS_TICK_SEC", "abc")
    assert reminder_loop._tick_interval() == 30
    monkeypatch.setenv("EVI_REMINDERS_TICK_SEC", "60")
    assert reminder_loop._tick_interval() == 60


def test_lifespan_starts_and_stops(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import main

    monkeypatch.setenv("EVI_API_KEY", "")
    monkeypatch.setenv("EVI_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TELEGRAM_MODE", "polling")
    with patch("services.reminder_loop.start_loop") as st, patch(
        "services.reminder_loop.stop_loop"
    ) as sp, patch("services.telegram_poller.start_poller") as pst, patch(
        "services.telegram_poller.stop_poller"
    ) as psp, patch.object(main, "build_agent_graph", return_value=MagicMock()):
        with TestClient(main.app):
            st.assert_called_once()
            pst.assert_called_once()
            sp.assert_not_called()
        sp.assert_called_once()
        psp.assert_called_once()


def test_stuck_thread_stays_referenced_and_no_second_thread():
    release = threading.Event()
    started = threading.Event()
    calls = []

    def blocking():
        calls.append(1)
        started.set()
        release.wait(5)

    with patch("services.reminders.fire_due", side_effect=blocking):
        assert reminder_loop.start_loop()
        assert started.wait(2)
        t = reminder_loop._thread
        reminder_loop.stop_loop(timeout=0.05)
        assert t.is_alive() and reminder_loop._thread is t  # not dropped while alive
        assert reminder_loop.start_loop() is True
        assert reminder_loop._thread is t and len(calls) == 1  # no second thread
        release.set()
        t.join(2)
        assert not t.is_alive()
        reminder_loop.stop_loop()
        assert reminder_loop._thread is None


def test_restart_uses_fresh_event():
    with patch("services.reminders.fire_due"):
        reminder_loop.start_loop()
        first = reminder_loop._stop
        reminder_loop.stop_loop()
        assert first.is_set()
        reminder_loop.start_loop()
        assert reminder_loop._stop is not first and not reminder_loop._stop.is_set()
