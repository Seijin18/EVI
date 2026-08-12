"""SCN-RT-03 — conversation memory is owned per session, never shared."""

import sys
import threading
from pathlib import Path

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.session_memory import (  # noqa: E402
    active_session_count,
    drop_session_memory,
    get_lane_lock,
    get_session_memory,
    normalize_session_id,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_for_tests()
    yield
    reset_for_tests()


def test_sessions_do_not_share_messages():
    a = get_session_memory("telegram-1")
    b = get_session_memory("whatsapp-2")

    a.add("a-first")
    b.add("b-first")
    a.add("a-second")

    assert a.get_messages() == ["a-first", "a-second"]
    assert b.get_messages() == ["b-first"]


def test_same_session_id_returns_same_buffer():
    first = get_session_memory("stable")
    first.add("kept")
    assert get_session_memory("stable") is first
    assert get_session_memory("stable").get_messages() == ["kept"]


def test_blank_session_id_normalizes_to_default():
    assert normalize_session_id(None) == "default"
    assert normalize_session_id("   ") == "default"
    assert get_session_memory(None) is get_session_memory("default")


def test_drop_session_memory_is_scoped():
    a = get_session_memory("drop-a")
    b = get_session_memory("drop-b")
    a.add("a")
    b.add("b")

    assert drop_session_memory("drop-a") is True
    assert drop_session_memory("drop-a") is False
    # b is untouched; a comes back empty
    assert get_session_memory("drop-b").get_messages() == ["b"]
    assert get_session_memory("drop-a").get_messages() == []


def test_clear_resets_on_trim_callback():
    """A trim callback captures a session_id by closure — it must not survive clear()."""
    fired = []
    memory = get_session_memory("trim")
    memory.set_on_trim(lambda: fired.append("leaked"))
    memory.clear()

    for i in range(memory.max_pairs * 2 + 4):
        memory.add(i)

    assert fired == []


def test_on_trim_fires_while_bound():
    fired = []
    memory = get_session_memory("trim-live")
    memory.set_on_trim(lambda: fired.append("ok"))

    for i in range(memory.max_pairs * 2 + 1):
        memory.add(i)

    assert fired  # capacity reached at least once


def test_registry_evicts_least_recently_used(monkeypatch):
    monkeypatch.setenv("EVI_SESSION_MEMORY_MAX", "3")
    for name in ("s1", "s2", "s3"):
        get_session_memory(name)
    get_session_memory("s1")  # refresh s1, making s2 the oldest
    get_session_memory("s4")

    assert active_session_count() == 3


def test_lane_lock_is_per_session_and_serializes():
    assert get_lane_lock("x") is get_lane_lock("x")
    assert get_lane_lock("x") is not get_lane_lock("y")

    lock = get_lane_lock("serial")
    order = []
    started = threading.Barrier(2)

    def worker(tag):
        started.wait()
        with lock:
            order.append(tag)

    threads = [threading.Thread(target=worker, args=(i,)) for i in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(order) == [1, 2]


def test_held_lane_lock_is_not_evicted(monkeypatch):
    monkeypatch.setenv("EVI_SESSION_MEMORY_MAX", "1")
    held = get_lane_lock("held")
    held.acquire()
    try:
        for name in ("other-1", "other-2", "other-3"):
            get_lane_lock(name)
        # Same object — a fresh lock here would break mutual exclusion.
        assert get_lane_lock("held") is held
        assert held.locked()
    finally:
        held.release()


def test_max_sessions_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("EVI_SESSION_MEMORY_MAX", "not-a-number")
    get_session_memory("ok")
    assert active_session_count() == 1

    monkeypatch.setenv("EVI_SESSION_MEMORY_MAX", "0")
    get_session_memory("still-ok")
    assert active_session_count() == 2


def test_buffer_carries_its_session_id():
    assert get_session_memory("tagged").session_id == "tagged"
    assert get_session_memory("  spaced  ").session_id == "spaced"
