import os
import sys
import threading
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.chat_commands import try_chat_command  # noqa: E402
from services.session_lane import session_lane  # noqa: E402


def test_chat_command_status():
    out = try_chat_command("/status", session_id="test")
    assert out and "EVI status" in out


def test_session_lane_serializes():
    order: list[int] = []
    barrier = threading.Barrier(2)

    def worker(n: int) -> None:
        with session_lane("same"):
            order.append(n)
            barrier.wait(timeout=2)

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert order == [1, 2] or order == [2, 1]
