"""Per-session serial queue (OpenClaw lane queue pattern).

The lock registry lives in `services/session_memory.py` so lane locks and session
buffers share one eviction policy; `session_lane` stays the public entry point.
"""

from __future__ import annotations

from contextlib import contextmanager

from services.session_memory import get_lane_lock


@contextmanager
def session_lane(session_id: str):
    """Serialize work for one session_id (in-process)."""
    lock = get_lane_lock(session_id)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
