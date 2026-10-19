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
    monkeypatch.setenv("EVI_SCHEDULED_TASKS_ENABLED", "false")
    monkeypatch.delenv("EVI_REMINDERS_TICK_SEC", raising=False)
    monkeypatch.delenv("EVI_PROMISE_CONTEXT_ENABLED", raising=False)
    monkeypatch.delenv("EVI_REPLY_DEBTS_ENABLED", raising=False)
    monkeypatch.setattr(reminder_loop, "release_stranded_promises", lambda: 0)
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


def test_promise_context_alone_starts_loop_without_firing_reminders(monkeypatch):
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "false")
    monkeypatch.setenv("EVI_PROMISE_CONTEXT_ENABLED", "true")
    done = threading.Event()
    with patch("services.reminders.fire_due") as fd, patch(
        "services.promise_context.process_due_evaluations", side_effect=lambda **kw: done.set()
    ) as pe:
        assert reminder_loop.start_loop() is True
        assert done.wait(2)
        assert fd.call_count == 0 and pe.call_count == 1


def test_start_loop_releases_stranded_promises_when_context_disabled(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("EVI_SCHEDULED_TASKS_ENABLED", "false")
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "false")
    monkeypatch.setenv("EVI_PROMISE_CONTEXT_ENABLED", "false")
    with patch("db.release_needs_eval", return_value=2) as rel:
        assert reminder_loop.start_loop() is False
        rel.assert_called_once()
    with patch("db.release_needs_eval", side_effect=RuntimeError("down")):
        assert reminder_loop.release_stranded_promises() == 0  # soft-fails


def test_maybe_sweep_runs_once_per_day_after_0645(monkeypatch):
    import datetime as dt

    monkeypatch.setenv("EVI_PROMISE_CONTEXT_ENABLED", "true")
    monkeypatch.setattr(reminder_loop, "_last_sweep_date", None)
    d = dt.datetime(2026, 10, 12, 6, 44)
    with patch("services.promise_context.sweep_fulfilled", return_value={}) as sw:
        assert reminder_loop._maybe_sweep(d) is False  # too early
        assert reminder_loop._maybe_sweep(d.replace(minute=45)) is True
        assert reminder_loop._maybe_sweep(d.replace(hour=9)) is False  # same day
        assert reminder_loop._maybe_sweep(d + dt.timedelta(days=1, hours=1)) is True
        assert sw.call_count == 2


def test_maybe_sweep_disabled_flag_and_failure_is_soft(monkeypatch):
    import datetime as dt

    monkeypatch.setattr(reminder_loop, "_last_sweep_date", None)
    d = dt.datetime(2026, 10, 12, 8, 0)
    monkeypatch.setenv("EVI_PROMISE_CONTEXT_ENABLED", "false")
    with patch("services.promise_context.sweep_fulfilled") as sw:
        assert reminder_loop._maybe_sweep(d) is False and sw.call_count == 0
    monkeypatch.setenv("EVI_PROMISE_CONTEXT_ENABLED", "true")
    with patch("services.promise_context.sweep_fulfilled", side_effect=RuntimeError("x")):
        assert reminder_loop._maybe_sweep(d) is True  # soft-fails, no raise


def test_promise_eval_interval_env_override(monkeypatch):
    monkeypatch.delenv("EVI_PROMISE_EVAL_TICK_SEC", raising=False)
    assert reminder_loop._promise_eval_interval() == reminder_loop.PROMISE_EVAL_EVERY_SEC
    monkeypatch.setenv("EVI_PROMISE_EVAL_TICK_SEC", "5")
    assert reminder_loop._promise_eval_interval() == 5.0
    monkeypatch.setenv("EVI_PROMISE_EVAL_TICK_SEC", "1")
    assert reminder_loop._promise_eval_interval() == reminder_loop.MIN_TICK_SEC
    monkeypatch.setenv("EVI_PROMISE_EVAL_TICK_SEC", "abc")
    assert reminder_loop._promise_eval_interval() == reminder_loop.PROMISE_EVAL_EVERY_SEC


# --- scheduled tasks hook (evi-scheduled-tasks, SCN-SCHED-02/04) -----------------


def test_scheduled_flag_alone_starts_loop_and_ticks_run_due(monkeypatch):
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "false")
    monkeypatch.setenv("EVI_SCHEDULED_TASKS_ENABLED", "true")
    called = threading.Event()
    with patch("services.scheduled_tasks.run_due", side_effect=lambda: called.set()) as rd:
        assert reminder_loop.start_loop() is True
        assert called.wait(2)  # first tick immediate
        assert rd.call_count == 1


def test_scheduled_flag_off_never_calls_run_due(monkeypatch):
    monkeypatch.setenv("EVI_SCHEDULED_TASKS_ENABLED", "false")
    fired = threading.Event()
    with patch("services.reminders.fire_due", side_effect=lambda: fired.set()), patch(
        "services.scheduled_tasks.run_due"
    ) as rd:
        reminder_loop.start_loop()
        assert fired.wait(2)
        assert rd.call_count == 0


def test_scheduled_check_is_rate_limited_and_isolated_from_reminders(monkeypatch):
    monkeypatch.setenv("EVI_SCHEDULED_TASKS_ENABLED", "true")
    monkeypatch.setattr(reminder_loop, "MIN_TICK_SEC", 0.01)
    monkeypatch.setenv("EVI_REMINDERS_TICK_SEC", "0.01")
    monkeypatch.setattr(reminder_loop, "SCHEDULED_EVERY_SEC", 3600.0)
    fd = MagicMock()
    with patch("services.reminders.fire_due", fd), patch(
        "services.scheduled_tasks.run_due", side_effect=RuntimeError("boom")
    ) as rd, patch.object(reminder_loop, "soft_fail"):
        reminder_loop.start_loop()
        assert _wait(lambda: fd.call_count >= 5)  # reminders keep ticking despite the failure
        assert rd.call_count == 1  # many ticks, one scheduled check (rate limit)
