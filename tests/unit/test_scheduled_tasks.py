"""SCN-SCHED-01..04 — scheduled tasks: service, caps, read-only turn, run_due."""

import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from sched_fakes import fake_db  # noqa: E402,F401
from services import scheduled_tasks as st  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")
# Wednesday 2026-10-14 12:00 local; next Friday 18:00 is 2026-10-16.
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=TZ)
FRI = datetime(2026, 10, 16, 18, 0, tzinfo=TZ)


@pytest.fixture(autouse=True)
def _drain_executor():
    """Let any still-running abandoned job finish and reset the in-flight set between tests."""
    yield
    st._get_executor().submit(lambda: None).result(10)
    with st._inflight_lock:
        st._inflight.clear()


class Sent:
    def __init__(self):
        self.msgs: list[str] = []

    def __call__(self, text, *a, **k):
        self.msgs.append(text)
        return True


def _create(prompt="resuma meus e-mails da semana", due=FRI, repeat="weekly", **kw):
    return st.create(prompt, due.isoformat(), repeat, now=NOW, **kw)


# --- 1.1 / SCN-SCHED-01 -----------------------------------------------------------


def test_create_stores_weekly_task_for_next_friday(fake_db):
    row, msg = _create()
    assert row and row["active"] and row["repeat"] == "weekly"
    assert row["next_at"] == FRI
    assert row["prompt"] == "resuma meus e-mails da semana"
    assert row["title"] == "resuma meus e-mails da semana"  # <= 6 words, derived
    assert "sex 16/10 às 18:00" in msg and "semanal" in msg


def test_title_derived_from_first_six_words_or_given(fake_db):
    row, _ = _create(prompt="um dois tres quatro cinco seis sete oito")
    assert row["title"] == "um dois tres quatro cinco seis…"
    row, _ = _create(prompt="x y", title="Meu título")
    assert row["title"] == "Meu título"


@pytest.mark.parametrize(
    "prompt,due,repeat",
    [("", FRI, ""), ("q", NOW - timedelta(days=1), ""), ("q", FRI, "hourly")],
)
def test_create_refuses_invalid(fake_db, prompt, due, repeat):
    row, msg = st.create(prompt, due.isoformat(), repeat, now=NOW)
    assert row is None and msg and not fake_db.rows


def test_cap_of_ten_active_tasks(fake_db):
    for i in range(st.MAX_ACTIVE):
        assert _create(prompt=f"t{i}")[0]
    row, msg = _create(prompt="onze")
    assert row is None and "10" in msg and len(fake_db.rows) == 10
    ok, _ = st.pause(1)
    assert ok
    assert _create(prompt="onze")[0]  # a paused task frees a slot


def test_list_cancel_pause_resume(fake_db):
    a, _ = _create(prompt="resumo semanal de e-mails")
    b, _ = _create(prompt="agenda de amanhã", repeat="daily", due=NOW + timedelta(hours=20))
    out = st.format_list()
    assert f"#{a['id']}" in out and f"#{b['id']}" in out
    assert st.pause("agenda")[0]
    assert "[pausada]" in st.format_list()
    ok, msg = st.resume(b["id"], now=NOW + timedelta(days=3))
    assert ok and fake_db.rows[b["id"]]["active"]
    assert fake_db.rows[b["id"]]["next_at"] > NOW + timedelta(days=3)  # next occurrence, no backfill
    assert st.cancel("resumo semanal de e-mails")[0]
    assert a["id"] not in fake_db.rows
    assert st.cancel("nada disso")[0] is False
    assert st.cancel(999)[0] is False


def test_ambiguous_title_asks_for_id(fake_db):
    _create(prompt="resumo semanal de e-mails")
    _create(prompt="resumo diário de e-mails")
    ok, msg = st.cancel("resumo")
    assert not ok and "Mais de uma" in msg and len(fake_db.rows) == 2


def test_resume_one_off_in_the_past_is_refused(fake_db):
    row, _ = _create(repeat="")
    st.pause(row["id"])
    ok, msg = st.resume(row["id"], now=FRI + timedelta(days=1))
    assert not ok and "passou" in msg


def test_flag_off_disables_everything(fake_db, monkeypatch):
    monkeypatch.setenv("EVI_SCHEDULED_TASKS_ENABLED", "false")
    assert _create()[0] is None
    assert st.run_due(now=FRI, send=Sent(), runner=lambda t: "x") == {
        "due": 0, "started": 0, "capped": 0, "skipped": 0,
    }


# --- 2.2 / SCN-SCHED-02 -----------------------------------------------------------


def test_due_task_delivered_with_title_and_next_friday(fake_db):
    row, _ = _create()
    sent = Sent()
    c = st.run_due(now=FRI + timedelta(seconds=5), send=sent,
                   runner=lambda t: f"Resumo: 3 e-mails ({t['prompt']})", wait=True)
    assert c["started"] == 1
    assert sent.msgs == [f"🗓 {row['title']}\nResumo: 3 e-mails ({row['prompt']})"]
    r = fake_db.rows[row["id"]]
    assert r["next_at"] == FRI + timedelta(days=7) and r["active"]
    assert r["last_status"] == "ok" and r["last_run_at"] is not None


def test_not_due_yet_does_nothing(fake_db):
    _create()
    sent = Sent()
    c = st.run_due(now=FRI - timedelta(minutes=1), send=sent, runner=lambda t: "x", wait=True)
    assert c["due"] == 0 and not sent.msgs


def test_one_shot_deactivates_after_run(fake_db):
    row, _ = _create(repeat="")
    st.run_due(now=FRI + timedelta(seconds=1), send=Sent(), runner=lambda t: "ok", wait=True)
    assert fake_db.rows[row["id"]]["active"] is False
    sent = Sent()
    assert st.run_due(now=FRI + timedelta(days=1), send=sent, runner=lambda t: "x", wait=True)["due"] == 0


def test_runs_off_the_calling_thread(fake_db):
    _create()
    seen = []
    st.run_due(now=FRI, send=Sent(), runner=lambda t: seen.append(threading.current_thread().name) or "x",
               wait=True)
    assert seen and seen[0] == "sched-run"
    assert threading.current_thread().name not in seen


def test_run_due_does_not_block_on_slow_task(fake_db):
    _create()
    gate = threading.Event()
    t0 = time.monotonic()
    st.run_due(now=FRI, send=Sent(), runner=lambda t: gate.wait(5) or "x")
    assert time.monotonic() - t0 < 1.0  # the loop thread returns immediately
    gate.set()


# --- failure / timeout ------------------------------------------------------------


def test_failure_notifies_once_and_advances(fake_db):
    row, _ = _create()
    sent = Sent()

    def boom(t):
        raise RuntimeError("llm down")

    st.run_due(now=FRI, send=sent, runner=boom, wait=True)
    assert sent.msgs == [f"Não consegui rodar '{row['title']}' agora; tento na próxima."]
    r = fake_db.rows[row["id"]]
    assert r["last_status"] == "error" and r["next_at"] == FRI + timedelta(days=7)
    st.run_due(now=FRI + timedelta(minutes=1), send=sent, runner=boom, wait=True)
    assert len(sent.msgs) == 1  # not due again: no repeated warning


def test_executor_timeout_is_a_failure(fake_db):
    row, _ = _create()
    sent = Sent()
    gate = threading.Event()
    t0 = time.monotonic()
    st.run_due(now=FRI, send=sent, runner=lambda t: gate.wait(5) or "late", wait=True, timeout=0.2)
    assert time.monotonic() - t0 < 2
    gate.set()
    assert sent.msgs == [f"Não consegui rodar '{row['title']}' agora; tento na próxima."]
    assert fake_db.rows[row["id"]]["last_status"] == "error"


# --- no overlap ---------------------------------------------------------------------


def test_same_occurrence_never_runs_twice_even_concurrently(fake_db):
    _create()
    calls = []
    gate = threading.Event()

    def slow(t):
        calls.append(t["id"])
        gate.wait(2)
        return "x"

    sent = Sent()
    results = []
    ts = [
        threading.Thread(
            target=lambda: results.append(st.run_due(now=FRI, send=sent, runner=slow, wait=True))
        )
        for _ in range(3)
    ]
    for t in ts:
        t.start()
    time.sleep(0.3)
    gate.set()
    for t in ts:
        t.join(5)
    assert calls == [1]
    assert sum(r["started"] for r in results) == 1


# --- SCN-SCHED-04: daily cap -----------------------------------------------------


def test_seventh_run_is_capped_told_once_and_runs_next_occurrence(fake_db):
    ids = [_create(prompt=f"tarefa {i}", repeat="daily", due=FRI)[0]["id"] for i in range(7)]
    sent = Sent()
    ran = []
    c = st.run_due(now=FRI, send=sent, runner=lambda t: ran.append(t["id"]) or "ok", wait=True)
    assert c["started"] == 6 and c["capped"] == 1
    assert ran == ids[:6]
    capped = [m for m in sent.msgs if m.startswith("Hoje já rodaram")]
    assert len(capped) == 1 and "'tarefa 6'" in capped[0]
    r7 = fake_db.rows[ids[6]]
    assert r7["last_status"] == "capped" and r7["last_run_at"] is None
    assert r7["next_at"] == FRI + timedelta(days=1) and r7["active"]
    # later the same day: nothing re-runs, nothing re-announced
    st.run_due(now=FRI + timedelta(hours=1), send=sent, runner=lambda t: "x", wait=True)
    assert len([m for m in sent.msgs if m.startswith("Hoje já rodaram")]) == 1
    # next day the capped task runs (counter is per local day)
    ran.clear()
    for i in ids[:6]:
        st.pause(i)  # so the 7th is not capped again by its six daily siblings
    st.run_due(now=FRI + timedelta(days=1, seconds=1), send=sent,
               runner=lambda t: ran.append(t["id"]) or "ok", wait=True)
    assert ids[6] in ran


def test_capped_one_shot_moves_to_next_day(fake_db):
    for i in range(6):
        _create(prompt=f"r{i}", repeat="daily", due=FRI)
    row, _ = _create(prompt="única", repeat="", due=FRI)
    st.run_due(now=FRI, send=Sent(), runner=lambda t: "ok", wait=True)
    r = fake_db.rows[row["id"]]
    assert r["active"] and r["next_at"] == FRI + timedelta(days=1)


# --- 2.1 / SCN-SCHED-03: read-only execution --------------------------------------


def test_read_only_tools_exclude_writes_and_scheduling():
    from services.write_guard import WRITE_TOOLS

    names = {t.name for t in st.read_only_tools()}
    assert names and not (names & WRITE_TOOLS)
    assert not (names & st._SCHEDULING_TOOLS)
    assert {"summarize_inbox", "list_calendar_events"} <= names
    assert "delete_emails_by_query" not in names


def test_scheduled_turn_cannot_delete_emails(fake_db, monkeypatch):
    """The model asks for delete_emails_by_query in a scheduled turn: not bound, not run."""
    import graph
    from langchain_core.messages import AIMessage
    from services import scheduled_tasks, turn_log, write_guard
    from tools import email_tool

    deleted = []
    monkeypatch.setattr(email_tool, "get_integration", lambda: deleted.append(1))
    bound: list[list[str]] = []
    seen_prompts: list[str] = []

    class FakeLLM:
        def __init__(self):
            self.n = 0

        def bind_tools(self, tools):
            bound.append([t.name for t in tools])
            return self

        def invoke(self, messages):
            self.n += 1
            if self.n == 1:
                seen_prompts.append(messages[0].content)
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "delete_emails_by_query", "args": {"q": "promo"}, "id": "c1"}],
                )
            return AIMessage(content="Não posso apagar nada numa tarefa agendada.")

    monkeypatch.setattr(graph, "llm", FakeLLM())
    monkeypatch.setattr(scheduled_tasks, "_graph_cache", None)
    monkeypatch.setenv("DATABASE_URL", "")
    row, _ = _create(prompt="apague meus e-mails de promoção", repeat="")
    out = st.run_turn(row)
    assert out == "Não posso apagar nada numa tarefa agendada."
    assert bound and "delete_emails_by_query" not in bound[0]
    assert not (set(bound[0]) & write_guard.WRITE_TOOLS)
    assert "Execução agendada pelo usuário" in seen_prompts[0]
    assert deleted == []  # no integration was ever reached
    # defense in depth: even called directly, the guard refuses in a scheduled turn
    _, token = turn_log.start_turn(channel="scheduled", session_id="scheduled:1")
    try:
        res = email_tool.delete_emails_by_query.invoke({"q": "promo"})
    finally:
        turn_log.end_turn(token)
    assert res.startswith(write_guard.BLOCKED_MESSAGE) and deleted == []
    scheduled_tasks._graph_cache = None


def test_run_turn_records_scheduled_turn_not_test(fake_db, monkeypatch):
    import graph
    from langchain_core.messages import AIMessage
    from services import scheduled_tasks, turn_log

    class FakeLLM:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            return AIMessage(content="ok")

    rec = {}
    monkeypatch.setattr(graph, "llm", FakeLLM())
    monkeypatch.setattr(scheduled_tasks, "_graph_cache", None)
    monkeypatch.setattr(turn_log, "record_turn", lambda c, **kw: rec.update(kw))
    row, _ = _create()
    assert st.run_turn(row) == "ok"
    assert rec["channel"] == "scheduled" and rec["is_test"] is False
    assert rec["session_id"] == f"scheduled:{row['id']}" and rec["reply_text"] == "ok"
    scheduled_tasks._graph_cache = None


def test_read_only_graph_is_cached(monkeypatch):
    from services import scheduled_tasks

    monkeypatch.setattr(scheduled_tasks, "_graph_cache", None)
    assert scheduled_tasks._graph() is scheduled_tasks._graph()
    scheduled_tasks._graph_cache = None
