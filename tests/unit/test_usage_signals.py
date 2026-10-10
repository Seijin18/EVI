"""SCN-USE-04: implicit usage signals (pure rules + idempotent job + retention)."""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services import usage_signals as us  # noqa: E402

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def turn(text, secs=0, reply="ok", tools=None, feedback=None, signals=None, sid="s"):
    return {
        "id": 1,
        "ts": T0 + timedelta(seconds=secs),
        "session_id": sid,
        "user_text": text,
        "reply_text": reply,
        "tools": tools or [],
        "feedback": feedback,
        "signals": signals or {},
    }


def test_rephrase_real_pair():
    a = turn("Você consegue listar meus compromissos?")
    b = turn("Listar compromissos", secs=40)
    assert us.similarity(a["user_text"], b["user_text"]) >= 0.6
    assert us.compute_signals(a, b) == {"rephrase": True}


def test_correction_real_phrase():
    a = turn("Qual o número da Beltrana?")
    b = turn("Esse número na verdade é de Fulana", secs=30)
    assert us.compute_signals(a, b) == {"correction": True}


@pytest.mark.parametrize(
    "text", ["Não era isso", "Errado", "não é isso", "Não foi isso que pedi", "Você errou"]
)
def test_correction_patterns(text):
    assert us.matches_correction(text)


@pytest.mark.parametrize("text", ["Não, obrigado", "Não", "Pode ser amanhã", "ótimo, valeu"])
def test_not_correction(text):
    assert not us.matches_correction(text)


def test_outside_window_no_signal():
    a = turn("Listar compromissos")
    assert us.compute_signals(a, turn("Listar compromissos", secs=181)) == {}
    assert us.compute_signals(a, turn("Listar compromissos", secs=180)) == {"rephrase": True}


def test_unrelated_next_turn():
    assert us.compute_signals(turn("Listar compromissos"), turn("Qual a previsão do tempo", 10)) == {}


def test_commands_excluded():
    a = turn("Listar compromissos")
    assert us.compute_signals(a, turn("/ruim", 5)) == {}
    assert us.compute_signals(turn("/ruim"), turn("Errado", 5)) == {}
    assert us.compute_signals(turn("/listar compromissos"), turn("Listar compromissos", 5)) == {}


def test_tool_failed_and_cant_do():
    a = turn(
        "x",
        reply="Desculpe, não tenho acesso à sua agenda.",
        tools=[{"name": "a", "ok": True}, {"name": "b", "ok": False, "reason": "timeout"}],
    )
    assert us.compute_signals(a, None) == {"tool_failed": True, "cant_do": True}
    assert us.compute_signals(turn("x", reply="Não posso fazer isso"), None) == {"cant_do": True}
    assert us.compute_signals(turn("x", reply=None), None) == {}


def test_turn_succeeded():
    assert us.turn_succeeded(turn("x"))
    assert us.turn_succeeded(turn("x", feedback="bom"))
    assert not us.turn_succeeded(turn("x", feedback="ruim"))
    assert not us.turn_succeeded(turn("x", signals={"rephrase": True}))
    assert not us.turn_succeeded(turn("x", signals={"tool_failed": True}))


# --- DB-backed --------------------------------------------------------------

needs_db = pytest.mark.ephemeral_db


@pytest.fixture
def db_ready():
    import db

    db.reset_db_init_for_tests()
    db.init_db()
    return db


def _set_ts(db, tid, ts):
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE turn_log SET ts = %s WHERE id = %s", (ts, tid))
        conn.commit()


@needs_db
def test_job_idempotent_scn_use_04(db_ready):
    db = db_ready
    sid = f"usg-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    a = db.insert_turn(session_id=sid, channel="api", user_text="Você consegue listar meus compromissos?")
    b = db.insert_turn(session_id=sid, channel="api", user_text="Listar compromissos")
    c = db.insert_turn(session_id=sid, channel="api", user_text="Qual o número da Beltrana?")
    d = db.insert_turn(session_id=sid, channel="api", user_text="Esse número na verdade é de Fulana")
    for tid, off in ((a, 300), (b, 260), (c, 100), (d, 70)):
        _set_ts(db, tid, now - timedelta(seconds=off))

    s1 = us.run_usage_signals()
    snap1 = {t: db.get_turn(t)["signals"] for t in (a, b, c, d)}
    s2 = us.run_usage_signals()
    snap2 = {t: db.get_turn(t)["signals"] for t in (a, b, c, d)}

    assert snap1 == snap2
    assert snap1[a] == {"rephrase": True}
    assert snap1[c] == {"correction": True}
    assert snap1[b] == {} and snap1[d] == {}
    assert s1["by_rule"]["rephrase"] >= 1 and s1["by_rule"]["correction"] >= 1
    assert s2["updated"] == 0

    # stale signals are overwritten, not appended
    db.update_turn_signals(b, {"cant_do": True})
    us.run_usage_signals()
    assert db.get_turn(b)["signals"] == {}


@needs_db
def test_prune_deletes_only_old(db_ready):
    db = db_ready
    sid = f"prune-{uuid.uuid4().hex[:8]}"
    old = db.insert_turn(session_id=sid, channel="api", user_text="velho")
    new = db.insert_turn(session_id=sid, channel="api", user_text="novo")
    _set_ts(db, old, datetime.now(timezone.utc) - timedelta(days=181))
    assert us.prune_turn_log(180) >= 1
    assert db.get_turn(old) is None
    assert db.get_turn(new) is not None
