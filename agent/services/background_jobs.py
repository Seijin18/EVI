"""Run slow cron jobs off the request thread so they never hold a Windmill worker.

Windmill runs a single worker. A scheduled script that POSTs a job and waits would
occupy that worker while the job calls back into Windmill (run_wait_result) -> deadlock.
So the endpoint starts the job in a thread and returns `{"status": "accepted"}` at once.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict

from services.soft_fail import soft_fail

_locks: Dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    with _registry_lock:
        return _locks.setdefault(name, threading.Lock())


def run_in_background(name: str, fn: Callable[..., Any], **kwargs: Any) -> Dict[str, Any]:
    """Start `fn(**kwargs)` in a daemon thread; at most one run per `name` at a time.

    Returns `{"status": "accepted", "job": name}` or `{"status": "already_running", "job": name}`.
    Exceptions inside the thread are soft-failed (logged), never raised.
    """
    lock = _lock_for(name)
    if not lock.acquire(blocking=False):
        return {"status": "already_running", "job": name}

    def _target() -> None:
        try:
            fn(**kwargs)
        except Exception as exc:
            soft_fail(f"background_jobs.{name}", exc)
        finally:
            lock.release()

    try:
        threading.Thread(target=_target, name=f"job-{name}", daemon=True).start()
    except Exception:
        lock.release()
        raise
    return {"status": "accepted", "job": name}


def run_inline(name: str, fn: Callable[..., Any], **kwargs: Any) -> Any:
    """Synchronous run (`wait=true`), sharing the per-name lock with background runs."""
    lock = _lock_for(name)
    if not lock.acquire(blocking=False):
        return {"status": "already_running", "job": name}
    try:
        return fn(**kwargs)
    finally:
        lock.release()
