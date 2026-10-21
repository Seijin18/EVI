"""SCN-INJ-03: write tools are allowlisted by turn origin, checked in code."""

from __future__ import annotations

import sys

import pytest

import db
from services import turn_log, write_guard
from tools.registry import get_all_tools

# Registered tools that do NOT mutate user data through an integration. A new tool
# must be added either here or to write_guard.WRITE_TOOLS (forces a decision).
READ_ONLY_TOOLS = {
    "list_calendar_events",
    "list_calendars",
    "list_tasks",
    "summarize_inbox",
    "list_pending_commitments",
    "list_scheduled_today",
    "query_conversation_graph",
    "list_whatsapp_contacts",
    "get_whatsapp_contact_info",
    "list_recent_whatsapp_messages",
    "summarize_whatsapp_messages",
    "list_reminders",
    "list_reply_debts",
    "query_university_notes",
    "list_scheduled_tasks",
}

# Minimal valid arguments per write tool.
ARGS = {
    "schedule_event": {"title": "x", "start_time": "2030-01-01T10:00:00"},
    "create_task": {"title": "x"},
    "complete_tasks": {"all_open": True},
    "delete_emails": {"message_ids": ["m1"]},
    "delete_emails_by_query": {"q": "promo"},
    "confirm_commitments": {"commitment_ids": [1]},
    "dismiss_commitments": {"commitment_ids": [1]},
    "set_whatsapp_contact_name": {"name_or_phone": "5511999999999", "display_name": "x"},
    "learn_whatsapp_contact": {"name_or_phone": "5511999999999"},
    "create_reminder": {"text": "x", "due_at": "2030-01-01T10:00:00"},
    "cancel_reminder": {"reminder_id": 1},
    "snooze_reminder": {"reminder_id": 1, "until": "2030-01-01T10:00:00"},
    "complete_reminder": {"reminder_id": 1},
    "create_scheduled_task": {"prompt": "x", "due_at": "2030-01-01T10:00:00"},
    "cancel_scheduled_task": {"id_or_title": "1"},
    "pause_scheduled_task": {"id_or_title": "1"},
    "resume_scheduled_task": {"id_or_title": "1"},
    "dismiss_reply_debt": {"jid_or_name": "x"},
    "organize_inbox": {"confirm": True},
    "save_note_manual": {"title": "x", "content": "y"},
    "ingest_university_pdf": {"file_path": "/nonexistent/x.pdf"},
    "ingest_university_folder": {"folder_path": "/nonexistent"},
}


def _tools():
    return {t.name: t for t in get_all_tools()}


def test_write_tools_are_registered():
    assert write_guard.WRITE_TOOLS <= set(_tools())


def test_every_registered_tool_is_classified():
    unknown = set(_tools()) - write_guard.WRITE_TOOLS - READ_ONLY_TOOLS
    assert not unknown, f"classify new tool(s) as write or read-only: {unknown}"
    assert not (write_guard.WRITE_TOOLS & READ_ONLY_TOOLS)
    assert set(ARGS) == set(write_guard.WRITE_TOOLS)


def _forbid_writes(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("write attempted")

    for name, mod in list(sys.modules.items()):
        if name.startswith("tools.") and hasattr(mod, "get_integration"):
            monkeypatch.setattr(mod, "get_integration", boom)
    monkeypatch.setattr(db, "init_db", boom)
    monkeypatch.setattr(db, "_conn", boom)


@pytest.mark.parametrize("channel", ["job", "scheduled"])
@pytest.mark.parametrize("name", sorted(write_guard.WRITE_TOOLS))
def test_write_tool_blocked_in_job_turn(name, channel, monkeypatch):
    tool = _tools()[name]
    _forbid_writes(monkeypatch)
    _, token = turn_log.start_turn(channel=channel, session_id="s-inj03")
    try:
        out = tool.invoke(ARGS[name])
    finally:
        turn_log.end_turn(token)
    assert out.startswith(write_guard.BLOCKED_MESSAGE)


@pytest.mark.parametrize("channel", ["telegram", "whatsapp_control", "api", None])
def test_user_channel_and_no_turn_pass_through(channel, monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return {}

    class Fake:
        post = staticmethod(fake_post)

    import tools.calendar_tool as cal

    monkeypatch.setattr(cal, "get_integration", lambda: Fake())
    token = None
    if channel:
        _, token = turn_log.start_turn(channel=channel, session_id="s-inj03")
    try:
        out = _tools()["schedule_event"].invoke(ARGS["schedule_event"])
    finally:
        if token is not None:
            turn_log.end_turn(token)
    assert calls, "tool body should have run"
    assert not str(out).startswith(write_guard.BLOCKED_MESSAGE)


def test_check_write_unknown_channel_blocked():
    _, token = turn_log.start_turn(channel="webhook", session_id="s")
    try:
        assert write_guard.check_write("create_task")
    finally:
        turn_log.end_turn(token)
    assert write_guard.check_write("create_task") is None


def test_decorator_keeps_schema_and_description():
    t = _tools()["create_task"]
    assert set(t.args) == {"title", "due_date", "notes"}
    assert t.description
    assert t.name == "create_task"


def test_scheduled_channel_refused_even_if_listed_as_user_channel(monkeypatch):
    """SCN-SCHED-03 defense in depth: the 'scheduled' refusal does not depend on USER_CHANNELS."""
    monkeypatch.setattr(write_guard, "USER_CHANNELS", write_guard.USER_CHANNELS | {"scheduled"})
    _, token = turn_log.start_turn(channel="scheduled", session_id="scheduled:1")
    try:
        assert write_guard.check_write("create_task").startswith(write_guard.BLOCKED_MESSAGE)
    finally:
        turn_log.end_turn(token)


def test_scheduled_tools_are_write_tools_except_listing():
    names = {t.name for t in get_all_tools()}
    sched = {n for n in names if n.endswith("_scheduled_task") or n.endswith("_scheduled_tasks")}
    assert sched == {
        "create_scheduled_task", "list_scheduled_tasks", "cancel_scheduled_task",
        "pause_scheduled_task", "resume_scheduled_task",
    }
    assert sched - {"list_scheduled_tasks"} <= write_guard.WRITE_TOOLS
