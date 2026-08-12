"""Per-session bounded memory and lane locks.

Replaces the process-wide `BoundedMemory` that every session used to share.
Both maps are keyed by `session_id` and capped by `EVI_SESSION_MEMORY_MAX`
(LRU eviction) so long-running processes do not grow without bound.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict

from memory import BoundedMemory

_DEFAULT_MAX_SESSIONS = 32
_MAX_PAIRS = 8

_lock = threading.Lock()
_memories: "OrderedDict[str, BoundedMemory]" = OrderedDict()
_lane_locks: "OrderedDict[str, threading.Lock]" = OrderedDict()


def normalize_session_id(session_id: str | None) -> str:
    return (session_id or "default").strip() or "default"


def _max_sessions() -> int:
    try:
        value = int(os.getenv("EVI_SESSION_MEMORY_MAX", str(_DEFAULT_MAX_SESSIONS)))
    except ValueError:
        return _DEFAULT_MAX_SESSIONS
    return value if value > 0 else _DEFAULT_MAX_SESSIONS


def _evict(store: OrderedDict) -> None:
    """Drop least-recently-used entries. Caller holds `_lock`."""
    limit = _max_sessions()
    while len(store) > limit:
        store.popitem(last=False)


def get_session_memory(session_id: str | None) -> BoundedMemory:
    """Return this session's own buffer, creating it on first use."""
    sid = normalize_session_id(session_id)
    with _lock:
        memory = _memories.get(sid)
        if memory is None:
            memory = BoundedMemory(max_pairs=_MAX_PAIRS, session_id=sid)
            _memories[sid] = memory
        else:
            _memories.move_to_end(sid)
        _evict(_memories)
    return memory


def drop_session_memory(session_id: str | None) -> bool:
    """Forget one session entirely. Returns True if it existed."""
    sid = normalize_session_id(session_id)
    with _lock:
        return _memories.pop(sid, None) is not None


def get_lane_lock(session_id: str | None) -> threading.Lock:
    """Return the serialization lock for one session_id."""
    sid = normalize_session_id(session_id)
    with _lock:
        lane = _lane_locks.get(sid)
        if lane is None:
            lane = threading.Lock()
            _lane_locks[sid] = lane
        else:
            _lane_locks.move_to_end(sid)
        # Never evict a lock that is currently held — a waiter would otherwise
        # get a fresh lock and run concurrently with the holder.
        limit = _max_sessions()
        while len(_lane_locks) > limit:
            oldest, candidate = next(iter(_lane_locks.items()))
            if oldest == sid or candidate.locked():
                break
            _lane_locks.popitem(last=False)
    return lane


def reset_for_tests() -> None:
    """Clear both registries (test isolation only)."""
    with _lock:
        _memories.clear()
        _lane_locks.clear()


def active_session_count() -> int:
    with _lock:
        return len(_memories)
