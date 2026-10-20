"""SCN-PREC-06/07 — regex-extracted tasks are judged by an LLM with conversation context."""

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services import promise_context as pc  # noqa: E402
from services import task_judge as tj  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 10, 12, 18, 0, tzinfo=TZ)  # Monday
JID = "5511999990000@s.whatsapp.net"
GENERIC = "As empresas gostam do fornecedor enviar a NF pra eles darem baixa no sistema"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    monkeypatch.delenv("EVI_TASK_JUDGE", raising=False)
    monkeypatch.delenv("EVI_REPLY_DEBTS_ENABLED", raising=False)
    monkeypatch.setattr(tj, "conversation_context", lambda *a, **k: {
        "contact": "Ana", "before": ["[14:00] Ana: fala do relatório?"], "after": [], "source": "evolution"})


# --- flag --------------------------------------------------------------------


def test_flag_default_on_needs_database_and_reply_debts(monkeypatch):
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert tj.task_judge_enabled() is False
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert tj.task_judge_enabled() is True
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "false")
    assert tj.task_judge_enabled() is False  # only undated tasks exist with reply debts on
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    for off in ("false", "0", "no", "OFF"):
        monkeypatch.setenv("EVI_TASK_JUDGE", off)
        assert tj.task_judge_enabled() is False


# --- evaluate_task -----------------------------------------------------------


def _llm(monkeypatch, out, seen=None):
    def fake(task, prompt, schema, **kw):
        assert task == "task"
        if seen is not None:
            seen.append(prompt)
        return out

    monkeypatch.setattr(tj.llm_structured, "run_structured", fake)


def _row(rid=1, text="te mando o relatório amanhã", age_h=1.0, **kw):
    ts = NOW - timedelta(hours=age_h)
    row = {
        "id": rid, "source_id": f"m{rid}", "source_chat": JID, "raw_text": text, "title": text,
        "msg_ts": ts, "created_at": ts, "event_date": None, "due_date": None, "source_label": "Ana",
        "next_eval_at": NOW - timedelta(minutes=1),
    }
    row.update(kw)
    return row


def test_prompt_has_context_question_rules_and_wrapped_candidate(monkeypatch):
    seen = []
    _llm(monkeypatch, {"keep": True, "title": "Enviar o relatório"}, seen)
    tj.evaluate_task(_row(), NOW)
    p = seen[0]
    assert "fala do relatório?" in p
    assert "que o USUÁRIO" in p and "As empresas gostam do fornecedor" in p  # question + generic example
    assert "«externo:whatsapp»" in p and "te mando o relatório amanhã" in p
    assert "«externo:whatsapp» Ana" in p.replace("\n", " ") or p.count("«externo:whatsapp»") > 2
    assert "entre o usuário (\"Você\") e «externo" in p  # contact display name is wrapped
    assert tj.PROMPT_VERSION == "v2"


def test_evaluate_task_title_validation(monkeypatch):
    _llm(monkeypatch, {"keep": True, "title": "enviar o relatório"})
    assert tj.evaluate_task(_row(), NOW) == {"keep": True, "title": "Enviar o relatório", "prompt_version": "v2"}
    _llm(monkeypatch, {"keep": True, "title": "x" * 61})
    assert tj.evaluate_task(_row(), NOW)["title"] is None  # too long: original title stays
    _llm(monkeypatch, {"keep": False, "title": "Enviar"})
    assert tj.evaluate_task(_row(), NOW)["title"] is None
    _llm(monkeypatch, None)
    assert tj.evaluate_task(_row(), NOW) is None
    _llm(monkeypatch, {"keep": "sim", "title": None})
    assert tj.evaluate_task(_row(), NOW) is None


# --- process_due_task_evaluations (fake queue) --------------------------------


class FakeQueue:
    def __init__(self, rows):
        self.rows = rows
        self.finished, self.bumped, self.extra = [], [], {}

    def list_stale_task_evals(self, cutoff, limit=100):
        return [r for r in self.rows if r["msg_ts"] < cutoff]

    def list_tasks_to_evaluate(self, now, limit=3):
        return [r for r in self.rows if r["next_eval_at"] <= now][:limit]

    def finish_promise_evaluation(self, rid, status, title=None, due_date=None, *, clear_due=False,
                                  clear_event=False, confirmed_via=None):
        self.rows[:] = [r for r in self.rows if r["id"] != rid]
        self.finished.append((rid, status, title))
        self.extra[rid] = confirmed_via
        self.cleared = getattr(self, "cleared", {})
        self.cleared[rid] = (clear_due, clear_event)
        return True

    def bump_promise_eval(self, rid, nxt):
        self.bumped.append((rid, nxt))
        return True


@pytest.fixture
def queue(monkeypatch):
    q = FakeQueue([])
    monkeypatch.setitem(sys.modules, "db", q)
    return q


def test_scn_prec_06_generic_sentence_is_dismissed_auto_eval(queue, monkeypatch):
    queue.rows[:] = [_row(1, GENERIC)]
    _llm(monkeypatch, {"keep": False, "title": None})
    assert tj.process_due_task_evaluations(NOW)["dismissed"] == 1
    assert queue.finished == [(1, "dismissed", None)] and queue.extra[1] == "auto-eval"


def test_scn_prec_07_kept_undated_task_gets_model_title(queue, monkeypatch):
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    queue.rows[:] = [_row(1, "te mando o relatório")]
    _llm(monkeypatch, {"keep": True, "title": "Enviar o relatório"})
    assert tj.process_due_task_evaluations(NOW)["kept"] == 1
    assert queue.finished == [(1, "undated", "Enviar o relatório")]


def test_kept_row_with_a_date_takes_pending(queue, monkeypatch):
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    queue.rows[:] = [_row(2, due_date="2026-10-13")]
    _llm(monkeypatch, {"keep": True, "title": None})
    tj.process_due_task_evaluations(NOW)
    assert queue.finished == [(2, "pending", None)]


def test_retry_cap_resolves_without_calling_the_llm(queue, monkeypatch):
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    queue.rows[:] = [_row(1, eval_attempts=6), _row(2, eval_attempts=5)]
    calls = []
    monkeypatch.setattr(tj, "evaluate_task", lambda row, now=None: calls.append(row["id"]))  # None = fail
    out = tj.process_due_task_evaluations(NOW)
    assert queue.finished == [(1, "undated", None)] and calls == [2]
    assert out["expired"] == 1 and out["retry"] == 1


def test_failure_retries_in_30_minutes(queue, monkeypatch):
    queue.rows[:] = [_row(1)]
    _llm(monkeypatch, None)
    assert tj.process_due_task_evaluations(NOW)["retry"] == 1
    assert queue.bumped == [(1, NOW + timedelta(minutes=30))] and queue.finished == []


def test_exception_in_row_is_bumped_not_raised(queue, monkeypatch):
    queue.rows[:] = [_row(1)]
    monkeypatch.setattr(tj, "evaluate_task", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert tj.process_due_task_evaluations(NOW)["error"] == 1
    assert queue.bumped and queue.finished == []


def test_after_48h_takes_pattern_status_with_original_title(queue, monkeypatch):
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    queue.rows[:] = [_row(1, age_h=49, due_date="2026-10-11"), _row(2, age_h=50),
                     _row(3, age_h=49, due_date="2026-10-20")]
    _llm(monkeypatch, AssertionError("llm must not run for stale rows"))
    out = tj.process_due_task_evaluations(NOW)
    assert out["expired"] == 3
    # past due cleared -> undated; future due kept -> pending; titles untouched
    assert queue.finished == [(1, "undated", None), (2, "undated", None), (3, "pending", None)]
    assert queue.cleared[1] == (True, False) and queue.cleared[3] == (False, False)


# --- promise/task queue separation (real DB) ----------------------------------


@pytest.mark.ephemeral_db
class TestQueueIsolation:
    @pytest.fixture(autouse=True)
    def _schema(self):
        import db

        db.reset_db_init_for_tests()
        db.init_db()

    def _insert(self, ctype, status="needs_eval", **kw):
        import db

        now = datetime.now(TZ)
        params = dict(
            source="test", source_id=f"src-{uuid.uuid4().hex[:12]}", ctype=ctype, title="x",
            status=status, source_chat=f"{uuid.uuid4().hex[:8]}@s.whatsapp.net",
            next_eval_at=now - timedelta(minutes=1), msg_ts=now - timedelta(hours=60),
        )
        params.update(kw)
        return db.insert_pending_commitment(**params)

    def test_promise_processor_ignores_tasks_and_vice_versa(self):
        import db

        now = datetime.now(TZ)
        task, promise = self._insert("task"), self._insert("promise")
        assert task in [r["id"] for r in db.list_tasks_to_evaluate(now, 500)]
        assert promise not in [r["id"] for r in db.list_tasks_to_evaluate(now, 500)]
        assert promise in [r["id"] for r in db.list_promises_to_evaluate(now, 500)]
        assert task not in [r["id"] for r in db.list_promises_to_evaluate(now, 500)]
        cutoff = now - timedelta(hours=48)
        assert task in [r["id"] for r in db.list_stale_task_evals(cutoff, 500)]
        assert task not in [r["id"] for r in db.list_stale_needs_eval(cutoff, 500)]
        assert promise in [r["id"] for r in db.list_stale_needs_eval(cutoff, 500)]

    def test_needs_eval_task_is_not_listed_or_counted(self):
        import db

        before = db.count_unnotified_pending()
        rid = self._insert("task", due_date="2099-01-01")
        assert rid not in [r["id"] for r in db.list_pending_commitments(limit=500)]
        assert rid not in [r["id"] for r in db.list_pending_commitments(limit=500, include_past=True)]
        assert db.count_unnotified_pending() == before

    def test_release_tasks_gives_pattern_status_and_spares_promises(self, monkeypatch):
        import db

        promise = self._insert("promise")
        dated = self._insert("task", due_date="2099-01-01")
        undated = self._insert("task")
        stale = self._insert("task", due_date="2020-01-01", event_date="2020-01-02")
        monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
        assert db.release_needs_eval_tasks() >= 3
        assert db.release_needs_eval() >= 1  # promises are released by their own path
        with db._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, status FROM pending_commitments WHERE id = ANY(%s)", ([promise, dated, undated, stale],))
            st = dict(cur.fetchall())
        assert st[dated] == "pending" and st[undated] == "undated" and st[promise] == "pending"
        assert st[stale] == "undated"  # past dates cleared

    def test_metrics_exclude_needs_eval_and_auto_eval_tasks(self):
        import db
        from services import usage_report

        since, until = datetime.now(TZ) - timedelta(hours=1), datetime.now(TZ) + timedelta(hours=1)
        base = db.action_rates_by_type(since, until, 1.0)["dated"]["shown"]
        dism = usage_report._fetch_commitments(since, until)["dismissed"]
        waiting, judged = self._insert("task"), self._insert("task")
        self._insert("task", status="pending")
        assert db.action_rates_by_type(since, until, 1.0)["dated"]["shown"] == base + 1  # needs_eval not counted
        db.finish_promise_evaluation(judged, "dismissed", confirmed_via="auto-eval")
        assert db.action_rates_by_type(since, until, 1.0)["dated"]["shown"] == base + 1  # auto-eval not counted
        assert usage_report._fetch_commitments(since, until)["dismissed"] == dism  # not a user dismissal
        human = self._insert("task", status="pending")
        db.update_commitment_status(human, "dismissed")
        assert usage_report._fetch_commitments(since, until)["dismissed"] == dism + 1
        assert waiting

    def test_process_end_to_end_dismisses_and_hides(self, monkeypatch):
        import db

        rid = self._insert("task", raw_text=GENERIC, source_id=f"e2e-{uuid.uuid4().hex[:8]}", msg_ts=datetime.now(TZ) - timedelta(hours=1))
        _llm(monkeypatch, {"keep": False, "title": None})
        out = tj.process_due_task_evaluations(datetime.now(TZ), batch=500)
        assert out["dismissed"] >= 1
        with db._conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT status, confirmed_via FROM pending_commitments WHERE id = %s", (rid,))
            assert cur.fetchone() == ("dismissed", "auto-eval")
        assert rid not in [r["id"] for r in db.list_pending_commitments(limit=500, include_past=True)]


# --- reminder loop hooks --------------------------------------------------------


def test_loop_releases_waiting_tasks_when_flag_off(monkeypatch):
    from services import reminder_loop

    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("EVI_TASK_JUDGE", "false")
    with patch("db.release_needs_eval_tasks", return_value=2) as rel:
        assert reminder_loop.release_stranded_tasks() == 2
        rel.assert_called_once()
    monkeypatch.setenv("EVI_TASK_JUDGE", "true")
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    with patch("db.release_needs_eval_tasks") as rel:
        assert reminder_loop.release_stranded_tasks() == 0
        rel.assert_not_called()


def test_loop_runs_task_judge_when_on(monkeypatch):
    import threading
    import time

    from services import reminder_loop

    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("EVI_TASK_JUDGE", "true")
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "false")
    monkeypatch.setenv("EVI_SCHEDULED_TASKS_ENABLED", "false")
    monkeypatch.setenv("EVI_PROMISE_CONTEXT_ENABLED", "false")
    monkeypatch.setattr(reminder_loop, "release_stranded_promises", lambda: 0)
    done = threading.Event()
    reminder_loop.stop_loop()
    with patch("services.task_judge.process_due_task_evaluations", side_effect=lambda **kw: done.set()) as pe, patch(
        "services.debt_judge.judge_enabled", return_value=False
    ):
        assert reminder_loop.start_loop() is True
        assert done.wait(2)
        reminder_loop.stop_loop()
        assert pe.call_args.kwargs == {"batch": 3}


# --- webhook insertion ------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import main
    from services.session_memory import reset_for_tests

    monkeypatch.setenv("EVI_API_KEY", "")
    monkeypatch.setenv("EVI_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    main.app_state.graph = MagicMock()
    reset_for_tests()
    return TestClient(main.app)


def _upsert(text, msg_id):
    return {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "5511888@s.whatsapp.net", "id": msg_id, "fromMe": False},
            "message": {"conversation": text},
            "messageTimestamp": 4102444800,
            "pushName": "Fulano",
        },
    }


def _post(client, payload):
    with patch("db.init_db"), \
         patch("db.insert_pending_commitment", return_value=7) as ins, \
         patch("services.commitment_review.maybe_notify_new_pending"), \
         patch("services.commitment_capture_notify.notify_commitment_captured") as notify, \
         patch("services.contact_filesystem.ingest_commitment") as ingest:
        r = client.post("/webhooks/evolution", json=payload)
    assert r.status_code == 200
    return ins, notify, ingest


def test_webhook_undated_task_waits_for_judge_without_notification(client):
    ins, notify, ingest = _post(client, _upsert("preciso mandar o relatório", "t1"))
    kw = ins.call_args.kwargs
    assert kw["ctype"] == "task" and kw["status"] == "needs_eval"
    assert kw["msg_ts"] is not None
    assert (kw["next_eval_at"] - kw["msg_ts"]) == timedelta(minutes=30)
    notify.assert_not_called()
    ingest.assert_not_called()


def test_webhook_dated_task_keeps_the_immediate_path(client):
    ins, notify, ingest = _post(client, _upsert("preciso mandar o relatório amanhã", "t4"))
    kw = ins.call_args.kwargs
    assert kw["ctype"] == "task" and kw["status"] == "pending" and "next_eval_at" not in kw
    ingest.assert_called_once()
    notify.assert_called_once()


def test_webhook_task_inserted_pending_when_judge_off(client, monkeypatch):
    monkeypatch.setenv("EVI_TASK_JUDGE", "off")
    ins, _, _ = _post(client, _upsert("preciso mandar o relatório", "t2"))
    kw = ins.call_args.kwargs
    assert kw["status"] == "undated" and "next_eval_at" not in kw


def test_webhook_event_never_goes_through_the_judge(client):
    ins, _, _ = _post(client, _upsert("Reunião com a equipe amanhã às 14h para revisar", "t3"))
    kw = ins.call_args.kwargs
    assert kw["ctype"] == "event" and kw["status"] == "pending" and "next_eval_at" not in kw
