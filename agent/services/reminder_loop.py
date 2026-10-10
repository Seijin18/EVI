"""In-process reminder loop: daemon thread ticking `reminders.fire_due`.

Started in the FastAPI lifespan only when EVI_REMINDERS_ENABLED is truthy. The first
tick runs immediately so reminders that fell due while the process was down are
delivered right away. Pacing uses Event.wait (monotonic, unaffected by libfaketime);
"now" is read inside fire_due via now_local().
"""

from __future__ import annotations

import logging
import os
import threading

from services.soft_fail import soft_fail

logger = logging.getLogger(__name__)

DEFAULT_TICK_SEC = 30.0
MIN_TICK_SEC = 5.0

_thread: threading.Thread | None = None
_stop = threading.Event()


def _tick_interval() -> float:
    raw = os.getenv("EVI_REMINDERS_TICK_SEC", "").strip()
    try:
        val = float(raw) if raw else DEFAULT_TICK_SEC
    except ValueError:
        val = DEFAULT_TICK_SEC
    return max(MIN_TICK_SEC, val)


def _run(stop: threading.Event, interval: float) -> None:
    from services import reminders

    while not stop.is_set():
        try:
            reminders.fire_due()
        except Exception as exc:
            soft_fail("reminder_loop.tick", exc)
        stop.wait(interval)


def start_loop() -> bool:
    """Start the daemon thread if enabled and DB configured. Idempotent."""
    global _thread
    from tools.reminder_tools import _reminders_enabled

    if not _reminders_enabled():
        return False
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL unset; reminder loop not started")
        return False
    if _thread and _thread.is_alive():
        return True
    _stop.clear()
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
    _stop.set()
    t = _thread
    if t and t.is_alive() and t is not threading.current_thread():
        t.join(timeout)
    _thread = None
