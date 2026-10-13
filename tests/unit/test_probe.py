"""SCN-USE-06 — daily read-only probe: one warning per failing integration per day."""

import ast
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

import db  # noqa: E402
from services import probe  # noqa: E402

OAUTH_ERR = "Windmill request failed: 400 Error refreshing token for Resource u/evi/gmail: invalid_grant"
OK_EVENTS = json.dumps({"status": "ok", "events": []})
OK_TASKS = json.dumps({"status": "ok", "tasks": []})
OK_INBOX = json.dumps({"status": "ok", "messages": []})
OK_BY_OP = {"list_events": OK_EVENTS, "list_tasks": OK_TASKS, "summarize_inbox": OK_INBOX}


class FakeIntegration:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def post(self, operation, payload, **kw):
        self.calls.append((operation, payload))
        r = self.responses[operation]
        if isinstance(r, Exception):
            raise r
        return r


class FakeDB:
    """In-memory stand-in for the probe_log helpers."""

    def __init__(self):
        self.rows = []
        self.notified = set()
        self.claimed = set()

    def insert_probe(self, day, check, ok, reason=None, ms=None):
        self.rows.append((day, check, ok, reason, ms))
        return len(self.rows)

    def probe_already_notified(self, day, check):
        return (day, check) in self.notified

    def mark_probe_notified(self, day, check):
        self.notified.add((day, check))

    def claim_probe_notification(self, day, check):
        if (day, check) in self.claimed:
            return False
        self.claimed.add((day, check))
        return True

    def release_probe_notification(self, day, check):
        self.claimed.discard((day, check))


@pytest.fixture
def env(monkeypatch):
    fake_db = FakeDB()
    for name in (
        "insert_probe", "probe_already_notified", "mark_probe_notified",
        "claim_probe_notification", "release_probe_notification",
    ):
        monkeypatch.setattr(db, name, getattr(fake_db, name))
    sent = []
    monkeypatch.setattr(
        "services.telegram_notify.send_telegram_message",
        lambda text, chat_id=None: sent.append(text) or True,
    )
    monkeypatch.setattr("services.telegram_poller._api_get", lambda token, method, params=None: {"ok": True})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    failures = []
    monkeypatch.setattr(probe.metrics, "record_probe_failure", failures.append)

    def install(responses):
        integ = FakeIntegration({**OK_BY_OP, **responses})
        monkeypatch.setattr(probe, "get_integration", lambda: integ)
        return integ

    return MagicMock(db=fake_db, sent=sent, failures=failures, install=install)


def test_all_ok_records_four_checks_read_only(env):
    integ = env.install({})
    out = probe.run_probe()
    assert out["ok"] is True
    assert set(out["checks"]) == {"calendar", "tasks", "gmail", "telegram"}
    assert [r[1] for r in env.db.rows] == ["calendar", "tasks", "gmail", "telegram"]
    assert all(r[2] and isinstance(r[4], int) for r in env.db.rows)
    assert env.sent == [] and env.failures == []
    ops = [c[0] for c in integ.calls]
    assert ops == ["list_events", "list_tasks", "summarize_inbox"]
    assert integ.calls[0][1]["on_date"] == out["day"]
    assert integ.calls[1][1]["max_results"] == 1
    assert integ.calls[2][1]["max_messages"] == 1


def test_scn_use_06_oauth_twice_one_warning(env):
    env.install({"summarize_inbox": OAUTH_ERR})
    first = probe.run_probe()
    second = probe.run_probe()
    assert first["checks"]["gmail"]["reason"] == "oauth"
    assert first["checks"]["gmail"]["notified"] is True
    assert second["checks"]["gmail"]["notified"] is False
    assert len(env.sent) == 1
    assert "Gmail" in env.sent[0] and "Windmill → Resources → gmail" in env.sent[0]
    assert env.failures == ["gmail", "gmail"]  # metric on every failure
    assert sum(1 for r in env.db.rows if r[1] == "gmail" and not r[2]) == 2


def test_failures_are_independent_and_soft(env):
    env.install({"list_events": RuntimeError("boom"), "list_tasks": "Missing WINDMILL_WEBHOOK_LIST_TASKS"})
    out = probe.run_probe()
    assert out["checks"]["calendar"]["ok"] is False
    assert out["checks"]["tasks"]["reason"] == "not_configured"
    assert out["checks"]["gmail"]["ok"] is True and out["checks"]["telegram"]["ok"] is True
    assert len(env.sent) == 2  # one per failing integration


def test_telegram_failure_recorded_not_notified(env, monkeypatch):
    env.install({})

    def down(token, method, params=None):
        raise OSError("unreachable")

    monkeypatch.setattr("services.telegram_poller._api_get", down)
    out = probe.run_probe()
    assert out["checks"]["telegram"]["ok"] is False
    assert out["checks"]["telegram"]["notified"] is False
    assert env.sent == [] and env.failures == ["telegram"]


def test_failed_send_is_not_marked_notified(env, monkeypatch):
    env.install({"summarize_inbox": OAUTH_ERR})
    monkeypatch.setattr("services.telegram_notify.send_telegram_message", lambda t, chat_id=None: False)
    probe.run_probe()
    assert env.db.notified == set()


def test_db_down_does_not_break_probe(env, monkeypatch):
    env.install({})

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "insert_probe", boom)
    assert probe.run_probe()["ok"] is True


def test_endpoint_mounting_pattern(env):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    env.install({})
    app = FastAPI()

    def verify_api_key():
        return None

    @app.post("/jobs/probe")
    def probe_job(_: None = Depends(verify_api_key)):
        from services.probe import run_probe

        return run_probe()

    r = TestClient(app).post("/jobs/probe")
    assert r.status_code == 200 and r.json()["ok"] is True


# --- read-only guard -----------------------------------------------------------

_FORBIDDEN_NAMES = {
    "schedule_event", "create_task", "create_task_result", "delete_emails",
    "delete_emails_by_query", "confirm_commitment", "dismiss_commitment",
    "send_whatsapp", "send_whatsapp_message", "send_text",
}
_FORBIDDEN_MODULE_PREFIXES = (
    "tools", "langchain", "services.evolution_client", "services.commitment_review",
    "services.commitment_notify", "services.direct_task", "services.direct_email",
    "services.whatsapp", "messaging",
)


def test_probe_module_imports_no_write_path():
    src = Path(probe.__file__).read_text(encoding="utf-8")
    bad = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods = [(a.name, None) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [(node.module or "", a.name) for a in node.names]
        else:
            continue
        for mod, name in mods:
            if mod.startswith(_FORBIDDEN_MODULE_PREFIXES) or (name in _FORBIDDEN_NAMES):
                bad.append((mod, name))
    assert not bad, f"probe must stay read-only, found imports: {bad}"
    # and it never names a write integration operation
    ops = {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not ops & {"schedule_event", "create_task", "delete_emails", "delete_emails_by_query"}


# --- DB-backed -----------------------------------------------------------------

PG_URL = os.getenv("DATABASE_URL", "")


@pytest.mark.ephemeral_db
def test_scn_use_06_real_db(monkeypatch):
    monkeypatch.setattr(db, "DATABASE_URL", PG_URL)
    db.reset_db_init_for_tests()
    db.init_db()
    sent = []
    monkeypatch.setattr(
        "services.telegram_notify.send_telegram_message",
        lambda text, chat_id=None: sent.append(text) or True,
    )
    monkeypatch.setattr("services.telegram_poller._api_get", lambda t, m, p=None: {"ok": True})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    # unique day so reruns against a persistent DB don't see earlier notified rows
    fake_day = __import__("datetime").date(2000, 1, 1) + __import__("datetime").timedelta(days=time.time_ns() % 8000)
    monkeypatch.setattr(probe, "_today", lambda: fake_day)
    integ = FakeIntegration({**OK_BY_OP, "summarize_inbox": OAUTH_ERR})
    monkeypatch.setattr(probe, "get_integration", lambda: integ)
    probe.run_probe()
    probe.run_probe()
    assert len(sent) == 1 and "Gmail" in sent[0]
    rows = [r for r in db.list_probes(fake_day, fake_day) if r["check_name"] == "gmail"]
    assert len(rows) == 2 and all(not r["ok"] and r["reason"] == "oauth" for r in rows)


@pytest.mark.ephemeral_db
def test_claim_probe_notification_race_and_release(monkeypatch):
    import datetime as dt
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(db, "DATABASE_URL", PG_URL)
    db.reset_db_init_for_tests()
    db.init_db()
    day = dt.date(2099, 6, 1)
    chk = f"race-{time.time_ns()}"
    try:
        with ThreadPoolExecutor(4) as ex:
            results = list(ex.map(lambda _: db.claim_probe_notification(day, chk), range(4)))
        assert results.count(True) == 1
        db.release_probe_notification(day, chk)
        assert db.claim_probe_notification(day, chk) is True
    finally:
        db.release_probe_notification(day, chk)


def test_notify_releases_claim_when_send_fails(env, monkeypatch):
    env.install({"summarize_inbox": OAUTH_ERR})
    monkeypatch.setattr("services.telegram_notify.send_telegram_message", lambda text, chat_id=None: False)
    probe.run_probe()
    assert env.db.claimed == set()  # released: the next run may retry


# --- SCN-REL-04: in-turn OAuth warning shares the probe's daily claim ---

from services import turn_log  # noqa: E402
from services.tool_result import parse_windmill_result  # noqa: E402


def _gmail_turn_hit(**start_kw):
    token = None
    if start_kw is not None:
        _, token = turn_log.start_turn(**start_kw)
    try:
        return parse_windmill_result(OAUTH_ERR, action="acessar o Gmail",
                                     resource_env="WINDMILL_GMAIL_RESOURCE", tool="summarize_inbox")
    finally:
        if token is not None:
            turn_log.end_turn(token)


def test_scn_rel_04_probe_plus_two_turns_one_warning(env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    env.install({"summarize_inbox": OAUTH_ERR})
    probe.run_probe()
    _gmail_turn_hit(channel="telegram")
    _gmail_turn_hit(channel="telegram")
    assert len([t for t in env.sent if "Gmail" in t]) == 1


def test_two_turns_without_probe_send_once(env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    _gmail_turn_hit(channel="telegram")
    _gmail_turn_hit(channel="telegram")
    assert len(env.sent) == 1 and "Windmill → Resources → gmail" in env.sent[0]


def test_outside_a_turn_no_send(env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    parse_windmill_result(OAUTH_ERR, action="acessar o Gmail",
                          resource_env="WINDMILL_GMAIL_RESOURCE", tool="summarize_inbox")
    assert env.sent == []


def test_test_turn_no_send(env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    _gmail_turn_hit(channel="telegram", is_test=True)
    assert env.sent == []


def test_no_database_url_no_send(env, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _gmail_turn_hit(channel="telegram")
    assert env.sent == []


def test_unmapped_tool_no_send(env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    _, tok = turn_log.start_turn(channel="telegram")
    try:
        parse_windmill_result(OAUTH_ERR, action="x", resource_env="WINDMILL_GMAIL_RESOURCE", tool="other")
    finally:
        turn_log.end_turn(tok)
    assert env.sent == []


def test_send_failure_releases_claim_in_turn(env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setattr("services.telegram_notify.send_telegram_message", lambda text, chat_id=None: False)
    _gmail_turn_hit(channel="telegram")
    assert env.db.claimed == set()


def test_notify_oauth_never_raises_in_turn(env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "claim_probe_notification", boom)
    res = _gmail_turn_hit(channel="telegram")
    assert res.reason == "oauth"


@pytest.mark.ephemeral_db
def test_scn_rel_04_db_backed(monkeypatch):
    sent = []
    monkeypatch.setattr("services.telegram_notify.send_telegram_message",
                        lambda text, chat_id=None: sent.append(text) or True)
    day = probe._today()
    db.release_probe_notification(day, "gmail")
    try:
        assert probe._notify(day, "gmail", "oauth", "") is True  # the probe
        _gmail_turn_hit(channel="telegram")
        _gmail_turn_hit(channel="telegram")
        assert len(sent) == 1
    finally:
        db.release_probe_notification(day, "gmail")


def test_scn_ux_01_probe_warning_is_human_and_machine_reason_stays_in_logs(env, caplog):
    import logging

    env.install({"list_events": "HTTP 502 Bad Gateway from upstream"})
    with caplog.at_level(logging.WARNING, logger="evi.probe"):
        out = probe.run_probe()
    reason = out["checks"]["calendar"]["reason"]
    msg = next(m for m in env.sent if "Calendar" in m)
    assert reason not in msg and "motivo" not in msg and "502" not in msg
    assert "make status" in msg
    assert any(reason in r.getMessage() for r in caplog.records)  # stable reason kept in the log


def test_scn_ux_01_oauth_warning_says_access_expired_and_where_to_reconnect(env):
    env.install({"summarize_inbox": OAUTH_ERR})
    probe.run_probe()
    msg = next(m for m in env.sent if "Gmail" in m)
    assert "O acesso ao Gmail expirou" in msg and "Windmill → Resources → gmail" in msg
