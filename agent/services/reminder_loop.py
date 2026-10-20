"""In-process reminder loop: daemon thread ticking `reminders.fire_due`.

Started in the FastAPI lifespan when EVI_REMINDERS_ENABLED is truthy, promise context
evaluation is on, or EVI_SCHEDULED_TASKS_ENABLED is not false (it also drains the
`needs_eval` promise and task queues, ≤1/min, and hands due scheduled tasks to their own
executor every 30 s). The first
tick runs immediately so reminders that fell due while the process was down are
delivered right away. Pacing uses Event.wait (monotonic, unaffected by libfaketime);
"now" is read inside fire_due via now_local().
"""

from __future__ import annotations

import logging
import os
import threading
import time

from services.soft_fail import soft_fail

logger = logging.getLogger(__name__)

DEFAULT_TICK_SEC = 30.0
MIN_TICK_SEC = 5.0
PROMISE_EVAL_EVERY_SEC = 60.0
PROMISE_EVAL_BATCH = 3
TASK_EVAL_BATCH = 3
SCHEDULED_EVERY_SEC = 30.0  # due scheduled tasks are claimed at most this often
SWEEP_HOUR, SWEEP_MINUTE = 6, 45  # daily fulfilment sweep, before the 07:00 briefing

_last_sweep_date: str | None = None

_thread: threading.Thread | None = None
_stop: threading.Event | None = None


def _tick_interval() -> float:
    raw = os.getenv("EVI_REMINDERS_TICK_SEC", "").strip()
    try:
        val = float(raw) if raw else DEFAULT_TICK_SEC
    except ValueError:
        val = DEFAULT_TICK_SEC
    return max(MIN_TICK_SEC, val)


def _promise_eval_interval() -> float:
    """Seconds between needs_eval sweeps (EVI_PROMISE_EVAL_TICK_SEC, min 5; the sim lowers it)."""
    try:
        val = float(os.getenv("EVI_PROMISE_EVAL_TICK_SEC", "").strip() or PROMISE_EVAL_EVERY_SEC)
    except ValueError:
        val = PROMISE_EVAL_EVERY_SEC
    return max(MIN_TICK_SEC, val)


def _promise_context_enabled() -> bool:
    try:
        from services.promises import promise_context_enabled

        return promise_context_enabled()
    except Exception as exc:  # noqa: BLE001
        soft_fail("reminder_loop.promise_flag", exc)
        return False


def _task_judge_on() -> bool:
    try:
        from services.task_judge import task_judge_enabled

        return task_judge_enabled()
    except Exception as exc:  # noqa: BLE001
        soft_fail("reminder_loop.task_judge_flag", exc)
        return False


def release_stranded_tasks() -> int:
    """Task judge off: waiting needs_eval tasks take their pattern status (never hidden)."""
    if _task_judge_on() or not os.getenv("DATABASE_URL"):
        return 0
    try:
        import db

        from tools.calendar_time import now_local

        return db.release_needs_eval_tasks(now_local().date().isoformat())
    except Exception as exc:  # noqa: BLE001
        soft_fail("reminder_loop.release_tasks", exc)
        return 0


def _reminders_on() -> bool:
    from tools.reminder_tools import _reminders_enabled

    return _reminders_enabled()


def _scheduled_on() -> bool:
    try:
        from services.scheduled_tasks import enabled

        return enabled()
    except Exception as exc:  # noqa: BLE001
        soft_fail("reminder_loop.scheduled_flag", exc)
        return False


def release_stranded_promises() -> int:
    """Promise context off: needs_eval rows would never be evaluated; make them pending."""
    if _promise_context_enabled() or not os.getenv("DATABASE_URL"):
        return 0
    try:
        import db
        from tools.calendar_time import now_local

        return db.release_needs_eval(now_local().date().isoformat())
    except Exception as exc:  # noqa: BLE001
        soft_fail("reminder_loop.release_needs_eval", exc)
        return 0


def _maybe_sweep(now=None) -> bool:
    """Run the fulfilment sweep once per local day, at/after 06:45. True when it ran."""
    global _last_sweep_date
    if now is None:
        from tools.calendar_time import now_local

        now = now_local()
    today = now.date().isoformat()
    if _last_sweep_date == today or (now.hour, now.minute) < (SWEEP_HOUR, SWEEP_MINUTE):
        return False
    if not _promise_context_enabled():
        return False
    _last_sweep_date = today  # set first: a failing sweep is not retried every minute
    try:
        from services import promise_context

        promise_context.sweep_fulfilled()
    except Exception as exc:  # noqa: BLE001
        soft_fail("reminder_loop.promise_sweep", exc)
    return True


def _run(stop: threading.Event, interval: float) -> None:
    from services import reminders

    last_eval = float("-inf")
    last_sched = float("-inf")
    while not stop.is_set():
        if _reminders_on():
            try:
                reminders.fire_due()
            except Exception as exc:
                soft_fail("reminder_loop.tick", exc)
        if time.monotonic() - last_sched >= SCHEDULED_EVERY_SEC and _scheduled_on():
            last_sched = time.monotonic()
            try:
                from services import scheduled_tasks

                # claims due rows and hands them to its own executor: never blocks the tick
                scheduled_tasks.run_due()
            except Exception as exc:
                soft_fail("reminder_loop.scheduled", exc)
        if time.monotonic() - last_eval >= _promise_eval_interval():
            last_eval = time.monotonic()
            if not _promise_context_enabled():
                release_stranded_promises()  # flag flipped off while running
            else:
                try:
                    from services import promise_context

                    promise_context.process_due_evaluations(limit=PROMISE_EVAL_BATCH)
                except Exception as exc:
                    soft_fail("reminder_loop.promise_eval", exc)
                try:
                    _maybe_sweep()
                except Exception as exc:
                    soft_fail("reminder_loop.promise_sweep_hook", exc)
            if not _task_judge_on():
                release_stranded_tasks()  # flag flipped off while running
            else:
                try:
                    from services import task_judge

                    task_judge.process_due_task_evaluations(batch=TASK_EVAL_BATCH)
                except Exception as exc:
                    soft_fail("reminder_loop.task_eval", exc)
            try:
                from services import debt_judge

                if debt_judge.judge_enabled():
                    debt_judge.judge_candidates(limit=1)  # after reminders fired; soft-fails inside
            except Exception as exc:
                soft_fail("reminder_loop.debt_judge", exc)
        stop.wait(interval)


def start_loop() -> bool:
    """Start the daemon thread if enabled and DB configured. Idempotent."""
    global _thread, _stop
    release_stranded_promises()
    release_stranded_tasks()
    if not (_reminders_on() or _promise_context_enabled() or _scheduled_on() or _task_judge_on()):
        return False
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL unset; reminder loop not started")
        return False
    if _thread and _thread.is_alive():
        return True
    _stop = threading.Event()  # fresh per start: an old, stuck thread keeps its own
    _thread = threading.Thread(
        target=_run,
        args=(_stop, _tick_interval()),
        name="reminder-loop",
        daemon=True,
    )
    _thread.start()
    return True


def stop_loop(timeout: float = 5) -> None:
    global _thread
    if _stop is not None:
        _stop.set()
    t = _thread
    if t and t.is_alive() and t is not threading.current_thread():
        t.join(timeout)
    if t and t.is_alive():
        # keep the reference so start_loop() cannot spawn a second ticking thread
        logger.warning("reminder loop did not stop within %ss", timeout)
        return
    _thread = None
