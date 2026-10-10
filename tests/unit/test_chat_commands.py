import os
import sys
import threading
import time
from pathlib import Path

import pytest

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


def test_feedback_commands_call_set_turn_feedback(monkeypatch):
    import db

    calls = []
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(
        db, "set_turn_feedback", lambda sid, fb, note=None: calls.append((sid, fb, note)) or 7
    )
    out = try_chat_command("/ruim marcou o dia errado", session_id="s1")
    assert out and "marcou o dia errado" in out and "\n" not in out
    out = try_chat_command("/bom", session_id="s1")
    assert out and "Anotado" in out
    assert calls == [("s1", "ruim", "marcou o dia errado"), ("s1", "bom", None)]


def test_feedback_without_turn_or_db_is_soft(monkeypatch):
    import db

    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(db, "set_turn_feedback", lambda *a, **k: None)
    assert try_chat_command("/bom", session_id="s1") == "Não encontrei um pedido anterior para avaliar."

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "set_turn_feedback", boom)
    assert try_chat_command("/ruim x", session_id="s1") == "Não encontrei um pedido anterior para avaliar."


PG_URL = os.getenv("DATABASE_URL", "")


@pytest.mark.ephemeral_db
def test_feedback_scn_use_03_real_db(monkeypatch):
    """SCN-USE-03: /ruim <motivo> marks the latest non-command turn."""
    import db

    monkeypatch.setattr(db, "DATABASE_URL", PG_URL)
    db.init_db()
    sid = f"test-feedback-{time.time_ns()}"
    db.insert_turn(session_id=sid, channel="telegram", user_text="Crie uma reunião amanhã", is_test=True)
    db.insert_turn(session_id=sid, channel="telegram", user_text="/status", is_test=True)
    out = try_chat_command("/ruim marcou o dia errado", session_id=sid)
    assert out and "marcou o dia errado" in out
    with db._conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT user_text, feedback, feedback_note FROM turn_log WHERE session_id=%s ORDER BY id",
            (sid,),
        )
        rows = cur.fetchall()
    assert rows[0] == ("Crie uma reunião amanhã", "ruim", "marcou o dia errado")
    assert rows[1][1] is None
    assert try_chat_command("/bom", session_id="nunca-existiu-xyz") == "Não encontrei um pedido anterior para avaliar."
