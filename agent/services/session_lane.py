"""Per-session serial queue (OpenClaw lane queue pattern)."""

from __future__ import annotations

import threading
from contextlib import contextmanager

_locks: dict[str, threading.Lock] = {}
_meta = threading.Lock()


@contextmanager
def session_lane(session_id: str):
    """Serialize work for one session_id (in-process)."""
    sid = (session_id or "default").strip() or "default"
    with _meta:
        lock = _locks.setdefault(sid, threading.Lock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
