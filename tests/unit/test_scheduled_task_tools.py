"""SCN-SCHED-01 — scheduled-task tools: create/list/pause/resume/cancel, guarded."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from sched_fakes import fake_db  # noqa: E402,F401
from services import turn_log, write_guard  # noqa: E402
from tools import scheduled_task_tools as tools  # noqa: E402
from tools.registry import get_all_tools  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")


def _due(days=2):
    d = (datetime.now(TZ) + timedelta(days=days)).replace(second=0, microsecond=0)
    return d.isoformat()


def test_tools_registered():
    names = {t.name for t in get_all_tools()}
    assert {
        "create_scheduled_task", "list_scheduled_tasks", "cancel_scheduled_task",
        "pause_scheduled_task", "resume_scheduled_task",
    } <= names


def test_create_list_pause_resume_cancel_roundtrip(fake_db):
    out = tools.create_scheduled_task.invoke(
        {"prompt": "resuma meus e-mails da semana", "due_at": _due(), "repeat": "weekly"}
    )
    assert "Tarefa agendada #1" in out and "semanal" in out
    row = fake_db.rows[1]
    assert row["active"] and row["repeat"] == "weekly" and row["prompt"] == "resuma meus e-mails da semana"
    assert "#1" in tools.list_scheduled_tasks.invoke({})
    assert "pausada" in tools.pause_scheduled_task.invoke({"id_or_title": "1"})
    assert not fake_db.rows[1]["active"]
    assert "retomada" in tools.resume_scheduled_task.invoke({"id_or_title": "resuma"})
    assert fake_db.rows[1]["active"]
    assert "cancelada" in tools.cancel_scheduled_task.invoke({"id_or_title": "1"})
    assert tools.list_scheduled_tasks.invoke({}) == "Nenhuma tarefa agendada."


def test_create_rejects_bad_input_and_cap(fake_db):
    assert "Não criei" in tools.create_scheduled_task.invoke({"prompt": "x", "due_at": "ontem"})
    assert "Não criei" in tools.create_scheduled_task.invoke(
        {"prompt": "x", "due_at": _due(), "repeat": "hourly"}
    )
    for i in range(10):
        tools.create_scheduled_task.invoke({"prompt": f"t{i}", "due_at": _due()})
    out = tools.create_scheduled_task.invoke({"prompt": "onze", "due_at": _due()})
    assert "10" in out and len(fake_db.rows) == 10


def test_test_session_does_not_schedule(fake_db):
    _, token = turn_log.start_turn(channel="api", session_id="test-abc", is_test=True, user_text="agenda")
    try:
        out = tools.create_scheduled_task.invoke({"prompt": "x", "due_at": _due()})
    finally:
        turn_log.end_turn(token)
    assert "teste" in out and not fake_db.rows


@pytest.mark.parametrize("channel", ["job", "scheduled", "webhook"])
def test_write_tools_refused_outside_user_channels(fake_db, channel):
    fake_db.create_scheduled_task("t", "p", datetime.now(TZ) + timedelta(days=1), None)
    _, token = turn_log.start_turn(channel=channel, session_id="s")
    try:
        outs = [
            tools.create_scheduled_task.invoke({"prompt": "x", "due_at": _due()}),
            tools.cancel_scheduled_task.invoke({"id_or_title": "1"}),
            tools.pause_scheduled_task.invoke({"id_or_title": "1"}),
            tools.resume_scheduled_task.invoke({"id_or_title": "1"}),
        ]
    finally:
        turn_log.end_turn(token)
    assert all(o.startswith(write_guard.BLOCKED_MESSAGE) for o in outs)
    assert list(fake_db.rows) == [1] and fake_db.rows[1]["active"]


def test_listing_is_not_guarded(fake_db):
    _, token = turn_log.start_turn(channel="job", session_id="s")
    try:
        assert tools.list_scheduled_tasks.invoke({}) == "Nenhuma tarefa agendada."
    finally:
        turn_log.end_turn(token)


@pytest.mark.parametrize("which", ["scheduled", "reminder"])
def test_forwarded_message_creates_nothing(fake_db, monkeypatch, which):
    """A forwarded Telegram message blanks the turn's user text: no task/reminder."""
    from tools import reminder_tools

    created = []
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "true")
    monkeypatch.setattr(reminder_tools, "create_reminder_now", lambda *a, **k: created.append(1) or (True, "x"))
    _, token = turn_log.start_turn(channel="telegram", session_id="s", user_text="")
    try:
        if which == "scheduled":
            out = tools.create_scheduled_task.invoke({"prompt": "x", "due_at": _due()})
        else:
            out = reminder_tools.create_reminder.invoke({"text": "x", "due_at": _due()})
    finally:
        turn_log.end_turn(token)
    assert out == write_guard.NO_USER_REQUEST_MESSAGE
    assert not fake_db.rows and not created


def test_own_message_still_creates(fake_db):
    _, token = turn_log.start_turn(channel="telegram", session_id="s", user_text="agenda isso")
    try:
        out = tools.create_scheduled_task.invoke({"prompt": "x", "due_at": _due()})
    finally:
        turn_log.end_turn(token)
    assert "Tarefa agendada" in out
