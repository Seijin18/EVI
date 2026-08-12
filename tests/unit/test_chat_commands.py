import os
import sys
import threading
import time
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.chat_commands import try_chat_command  # noqa: E402
from services.session_lane import session_lane  # noqa: E402


def test_chat_command_status():
    out = try_chat_command("/status", session_id="test")
    assert out and "EVI status" in out


def test_session_lane_serializes():
    """Two turns on one session_id must never be inside the lane at once.

    The barrier belongs outside the lane — releasing both threads at the same
    instant so they genuinely contend. Putting it inside means the first holder
    waits for a thread the lock is keeping out, and the test only finishes when
    the barrier times out.
    """
    order: list[int] = []
    inside = 0
    overlapped = False
    guard = threading.Lock()
    start = threading.Barrier(2, timeout=5)

    def worker(n: int) -> None:
        nonlocal inside, overlapped
        start.wait()
        with session_lane("same"):
            with guard:
                inside += 1
                if inside > 1:
                    overlapped = True
            order.append(n)
            time.sleep(0.05)  # widen the window an unserialized lane would expose
            with guard:
                inside -= 1

    threads = [threading.Thread(target=worker, args=(n,)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()

    assert not overlapped, "two threads were inside the same lane at once"
    assert sorted(order) == [1, 2]


def test_session_lane_does_not_serialize_across_sessions():
    """Different session_ids must run concurrently — that is the whole point."""
    both_inside = threading.Barrier(2, timeout=5)
    errors: list[BaseException] = []

    def worker(session_id: str) -> None:
        try:
            with session_lane(session_id):
                # Only clears if the other session is inside its lane too.
                both_inside.wait()
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(sid,))
        for sid in ("lane-a", "lane-b")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()

    assert not errors, f"sessions blocked each other: {errors}"
