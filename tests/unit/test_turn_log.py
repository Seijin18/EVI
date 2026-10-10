"""SCN-USE-01 — every /chat turn is recorded in turn_log, tools with their outcome.

A real LangGraph (fake chat model, real `schedule_event` tool, ToolNode running
it in its own executor context) proves the ContextVar collector survives the
thread hop. The DB round-trip tests skip without `DATABASE_URL`.
"""

import operator
import sys
import uuid
from pathlib import Path
from typing import Annotated, TypedDict
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import END, StateGraph  # noqa: E402
from langgraph.prebuilt import ToolNode  # noqa: E402

import db  # noqa: E402,F401  (imported with the real DATABASE_URL, before any monkeypatch)
import main  # noqa: E402
from main import ChatRequest, app_state  # noqa: E402
from services import turn_log  # noqa: E402
from services.session_memory import reset_for_tests  # noqa: E402
from tools.calendar_tool import schedule_event  # noqa: E402


@tool
def save_note_stub(title: str) -> str:
    """A tool with no Windmill behind it."""
    return f"saved {title}"


class _State(TypedDict):
    messages: Annotated[list, operator.add]
    task_type: str
    iterations: int
    final_answer: str
    extra_context: str


def _graph(tool_calls: list[dict], final: str = "Pronto."):
    """agent -> tools -> agent, with scripted model replies."""
    replies = iter(
        [AIMessage(content="", tool_calls=tool_calls), AIMessage(content=final)]
        if tool_calls
        else [AIMessage(content=final)]
    )
    model = GenericFakeChatModel(messages=replies)

    def agent(state):
        return {"messages": [model.invoke(state["messages"])]}

    def route(state):
        return "tools" if getattr(state["messages"][-1], "tool_calls", None) else END

    g = StateGraph(_State)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode([schedule_event, save_note_stub]))
    g.set_entry_point("agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile()


_SCHEDULE = {
    "name": "schedule_event",
    "args": {
        "title": "Dentista",
        "start_time": "2026-06-10T15:00:00",
        "end_time": "2026-06-10T16:00:00",
    },
    "id": "c1",
}
_OAUTH_RAW = "Error refreshing token: invalid_grant"


@pytest.fixture
def windmill_oauth_error():
    integ = MagicMock()
    integ.post.return_value = _OAUTH_RAW
    with patch("tools.calendar_tool.get_integration", return_value=integ):
        yield


@pytest.fixture(autouse=True)
def _fresh_memory():
    reset_for_tests()


def _run(session_id="tg-1", channel="telegram"):
    return main._chat_impl(ChatRequest(message="Marque dentista", session_id=session_id), session_id, channel)


def test_oauth_failure_is_recorded_with_reason_and_channel(monkeypatch, windmill_oauth_error):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    app_state.graph = _graph([_SCHEDULE])
    with patch("db.insert_turn") as insert:
        out = _run()
    assert out["response"] == "Pronto."
    kw = insert.call_args.kwargs
    assert kw["channel"] == "telegram" and kw["session_id"] == "tg-1"
    assert kw["user_text"] == "Marque dentista" and kw["reply_text"] == "Pronto."
    assert kw["is_test"] is False and kw["error"] is None
    assert kw["llm_calls"] == 2
    assert isinstance(kw["latency_ms"], int)
    [t] = kw["tools"]
    assert (t["name"], t["ok"], t["reason"]) == ("schedule_event", False, "oauth")
    assert isinstance(t["ms"], int)


def test_tool_without_windmill_has_unknown_outcome(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    app_state.graph = _graph([{"name": "save_note_stub", "args": {"title": "x"}, "id": "c2"}])
    with patch("db.insert_turn") as insert:
        _run(channel="whatsapp_control")
    kw = insert.call_args.kwargs
    assert kw["channel"] == "whatsapp_control"
    [t] = kw["tools"]
    assert t["name"] == "save_note_stub" and t["ok"] is None and t["reason"] is None


def test_db_failure_while_recording_still_delivers_the_reply(monkeypatch, windmill_oauth_error):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    app_state.graph = _graph([_SCHEDULE])
    with patch("db.insert_turn", side_effect=RuntimeError("db down")):
        out = _run()
    assert out["response"] == "Pronto."


def test_no_database_url_is_a_noop(monkeypatch, windmill_oauth_error):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app_state.graph = _graph([])
    with patch("db.insert_turn") as insert:
        assert _run()["response"] == "Pronto."
    insert.assert_not_called()


def test_failed_turn_is_recorded_with_error_and_still_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    app_state.graph = MagicMock()
    app_state.graph.invoke.side_effect = RuntimeError("boom")
    with patch("db.insert_turn") as insert:
        with pytest.raises(main.HTTPException):
            _run()
    kw = insert.call_args.kwargs
    assert kw["error"] == "boom" and kw["reply_text"] is None


def test_http_route_uses_api_channel_and_whatsapp_wrapper_its_own(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    with patch("db.insert_turn") as insert:
        app_state.graph = _graph([])
        main.chat(ChatRequest(message="oi", session_id="s-api"))
        app_state.graph = _graph([])
        main._whatsapp_control_invoke_chat("oi", "s-wa")
        app_state.graph = _graph([])
        main._telegram_invoke_chat("oi", "s-tg")
    assert [c.kwargs["channel"] for c in insert.call_args_list] == [
        "api",
        "whatsapp_control",
        "telegram",
    ]


@pytest.mark.parametrize(
    "sid,expected",
    [
        ("evi-test-20260101", True),
        ("test-abc", True),
        ("health-check", True),
        ("tg-digest-verify", True),
        ("tg-12345", False),
        ("default", False),
        (None, False),
    ],
)
def test_is_test_session(sid, expected):
    assert turn_log.is_test_session(sid) is expected


def test_outcome_outside_a_turn_is_ignored():
    turn_log.record_tool_outcome("schedule_event", False, "oauth")  # must not raise


# --- real Postgres ----------------------------------------------------------

needs_db = pytest.mark.ephemeral_db


@needs_db
def test_turn_row_really_lands_in_postgres(windmill_oauth_error):
    db.reset_db_init_for_tests()
    db.init_db()
    sid = f"evi-test-{uuid.uuid4().hex[:8]}"
    app_state.graph = _graph([_SCHEDULE])
    _run(session_id=sid, channel="telegram")
    with db._conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT channel, reply_text, tools, llm_calls, is_test FROM turn_log WHERE session_id=%s",
            (sid,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    channel, reply, tools, llm_calls, is_test = rows[0]
    assert channel == "telegram" and reply == "Pronto." and llm_calls == 2 and is_test is True
    assert tools[0]["name"] == "schedule_event" and tools[0]["ok"] is False
    assert tools[0]["reason"] == "oauth"
