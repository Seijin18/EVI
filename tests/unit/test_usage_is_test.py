"""SCN-USE-02 — harness turns are is_test and never reach KPIs/metrics."""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

import main  # noqa: E402
from services import turn_log  # noqa: E402
from testing import cleanup  # noqa: E402

PG = "postgresql://postgres:t@127.0.0.1:55432/fresh2"


def _record(**kw):
    base = dict(session_id="real-1", channel="api", user_text="oi", reply_text="r", latency_ms=1)
    base.update(kw)
    with patch.dict(os.environ, {"DATABASE_URL": "x"}), patch("db.insert_turn") as ins, patch(
        "services.metrics.record_turn"
    ) as met:
        turn_log.record_turn(None, **base)
    return ins, met


def test_header_parsing():
    assert main._header_is_test("1") and main._header_is_test("true")
    assert not main._header_is_test(None) and not main._header_is_test("0")


def test_explicit_flag_and_prefix():
    assert _record(is_test=True)[0].call_args.kwargs["is_test"] is True
    assert _record()[0].call_args.kwargs["is_test"] is False
    for p in turn_log.TEST_SESSION_PREFIXES:
        assert _record(session_id=p + "x")[0].call_args.kwargs["is_test"] is True


def test_metrics_outcomes_and_skip_for_tests():
    assert _record()[1].call_args.args == ("api", "ok")
    assert _record(error="boom")[1].call_args.args == ("api", "error")
    col = MagicMock()
    col.tools.return_value = [{"name": "t", "ok": False}]
    with patch.dict(os.environ, {"DATABASE_URL": ""}), patch("services.metrics.record_turn") as met:
        turn_log.record_turn(col, session_id="s", channel="telegram", user_text="u",
                             reply_text="r", latency_ms=1)
    assert met.call_args.args == ("telegram", "tool_failed")
    assert not _record(is_test=True)[1].called
    assert not _record(session_id="test-abc")[1].called


def test_chat_route_header_reaches_record_turn():
    from fastapi.testclient import TestClient

    main.app_state.graph = MagicMock()
    with patch("main._chat_turn", return_value={"response": "ok"}), patch(
        "services.turn_log.record_turn"
    ) as rec:
        c = TestClient(main.app)
        c.post("/chat", json={"message": "a", "session_id": "real-x"}, headers={"X-Evi-Test": "1"})
        c.post("/chat", json={"message": "b", "session_id": "real-y"})
    assert rec.call_args_list[0].kwargs["is_test"] is True
    assert rec.call_args_list[1].kwargs["is_test"] is False


def test_cleanup_prefixes_match_turn_log():
    assert cleanup.TEST_SESSION_PREFIXES == turn_log.TEST_SESSION_PREFIXES


def test_cleanup_sql_against_postgres():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        conn = psycopg2.connect(PG, connect_timeout=2)
    except Exception:
        pytest.skip("ephemeral PG unavailable")
    import db

    with patch.object(db, "DATABASE_URL", PG):
        db.init_db()

    tag = uuid.uuid4().hex[:8]
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO turn_log (session_id,channel,user_text,is_test) VALUES ('s','api',%s,true),('s','api',%s,false)", (f"T{tag}", f"R{tag}"))
            cur.execute("INSERT INTO messages (session_id,role,content) VALUES (%s,'user','x'),(%s,'user','x'),(%s,'user','x')",
                        (f"test-{tag}", f"tg-digest-verify-{tag}", f"testimony-{tag}"))
            cur.execute("INSERT INTO pending_commitments (source,source_id,type,title) VALUES ('evi-test',%s,'event','Teste digest Telegram'),('whatsapp',%s,'event','real'),('evi-test','other','event','keep')",
                        (f"tg-digest-verify-{tag}", f"tg-digest-verify-{tag}"))
        conn.commit()
        lines = []
        base = cleanup.run(conn, apply=False, out=lines.append)
        assert base["turn_log"] >= 1 and base["messages"] >= 2 and base["pending_commitments"] >= 1
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM turn_log WHERE user_text=%s", (f"T{tag}",))
            assert cur.fetchone()[0] == 1  # dry run kept it
        cleanup.run(conn, apply=True, out=lines.append)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM turn_log WHERE user_text IN (%s,%s)", (f"T{tag}", f"R{tag}"))
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT session_id FROM messages WHERE session_id LIKE %s", (f"%{tag}",))
            assert [r[0] for r in cur.fetchall()] == [f"testimony-{tag}"]
            cur.execute("SELECT source, source_id FROM pending_commitments WHERE source_id IN (%s,'other')", (f"tg-digest-verify-{tag}",))
            assert sorted(cur.fetchall()) == [("evi-test", "other"), ("whatsapp", f"tg-digest-verify-{tag}")]
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM turn_log WHERE user_text IN (%s,%s)", (f"T{tag}", f"R{tag}"))
            cur.execute("DELETE FROM messages WHERE session_id LIKE %s", (f"%{tag}",))
            cur.execute("DELETE FROM pending_commitments WHERE source_id IN (%s,'other')", (f"tg-digest-verify-{tag}",))
        conn.commit()
        conn.close()
