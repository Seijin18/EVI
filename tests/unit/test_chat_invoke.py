"""Integration tests for /chat invoke (runtime v3 context + tool snapshots)."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

import main  # noqa: E402
from main import ChatRequest, app_state, chat  # noqa: E402
from services.session_memory import reset_for_tests  # noqa: E402


def _mock_graph_result():
    human = HumanMessage(content="Revise meus emails")
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "summarize_inbox", "args": {"max_messages": 10}, "id": "call1"}],
    )
    tool = ToolMessage(
        content=json.dumps(
            {"status": "ok", "messages": [{"id": "chat001", "subject": "Test"}]}
        ),
        name="summarize_inbox",
        tool_call_id="call1",
    )
    final = AIMessage(content="Você tem 1 email recente.")
    return {
        "messages": [human, ai, tool, final],
        "final_answer": "Você tem 1 email recente.",
    }


def test_chat_injects_extra_context_and_returns_tools():
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = _mock_graph_result()
    app_state.graph = mock_graph
    reset_for_tests()

    with patch("services.context_assembly.build_context", return_value="PROJECT CONTEXT:\ntest") as mock_ctx:
        result = chat(ChatRequest(message="Revise meus emails", session_id="test-chat-1"))

    mock_ctx.assert_called_once_with("test-chat-1", "Revise meus emails")
    state = mock_graph.invoke.call_args[0][0]
    assert state.get("extra_context") == "PROJECT CONTEXT:\ntest"
    assert result["session_id"] == "test-chat-1"
    assert "response" in result
    assert result["response"] == "Você tem 1 email recente."
    assert any(t.get("tool") == "summarize_inbox" for t in result["tools"])


def test_chat_persists_tool_snapshots():
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = _mock_graph_result()
    app_state.graph = mock_graph
    reset_for_tests()

    with patch("services.context_assembly.build_context", return_value=""):
        with patch("db.init_db"), patch("db.save_tool_snapshot") as save:
            chat(ChatRequest(message="Revise meus emails", session_id="snap-session"))

    save.assert_called()
    args = save.call_args[0]
    assert args[0] == "snap-session"
    assert args[1] == "summarize_inbox"
    payload = args[2]
    assert payload.get("messages") or payload.get("status") == "ok"


def test_chat_snapshot_round_trip_in_context():
    from services.context_assembly import build_context
    from services.session_context import persist_tool_snapshots

    tool = ToolMessage(
        content=json.dumps({"status": "ok", "messages": [{"id": "round001"}]}),
        name="summarize_inbox",
        tool_call_id="c1",
    )
    sid = "round-trip-session"

    with patch("db.init_db"), patch("db.save_tool_snapshot") as save:
        with patch("db.load_tool_snapshots") as load:
            load.return_value = [
                {
                    "tool_name": "summarize_inbox",
                    "payload": {"status": "ok", "messages": [{"id": "round001"}]},
                }
            ]
            ctx = build_context(sid, "apaga o primeiro")
    assert "SESSION TOOL SNAPSHOTS" in ctx
    assert "round001" in ctx


def test_chat_http_client():
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = _mock_graph_result()
    app_state.graph = mock_graph
    reset_for_tests()

    from fastapi.testclient import TestClient

    with patch("services.context_assembly.build_context", return_value="ctx"):
        client = TestClient(main.app)
        r = client.post(
            "/chat",
            json={"message": "ping", "session_id": "http-session"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "http-session"
    assert "tools" in body


def test_chat_keeps_sessions_isolated():
    """SCN-RT-03 — two sessions through /chat never see each other's messages."""
    from services.session_memory import get_session_memory

    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = lambda state: {
        "messages": [AIMessage(content="ok")],
        "final_answer": "ok",
    }
    app_state.graph = mock_graph
    reset_for_tests()

    with patch("services.context_assembly.build_context", return_value=""):
        chat(ChatRequest(message="sou A", session_id="iso-A"))
        chat(ChatRequest(message="sou B", session_id="iso-B"))

    a_text = " ".join(str(m.content) for m in get_session_memory("iso-A").get_messages())
    b_text = " ".join(str(m.content) for m in get_session_memory("iso-B").get_messages())
    assert "sou B" not in a_text
    assert "sou A" not in b_text


def test_reset_only_clears_requested_session():
    """SCN-RESET-01 — /reset on one channel must not wipe the others."""
    from services.session_memory import get_session_memory

    reset_for_tests()
    get_session_memory("reset-A").add(HumanMessage(content="a"))
    get_session_memory("reset-B").add(HumanMessage(content="b"))

    body = main.reset_memory(main.ResetRequest(session_id="reset-A"))

    assert body["session_id"] == "reset-A"
    assert body["existed"] is True
    assert get_session_memory("reset-A").get_messages() == []
    assert len(get_session_memory("reset-B").get_messages()) == 1


if __name__ == "__main__":
    test_chat_injects_extra_context_and_returns_tools()
    test_chat_persists_tool_snapshots()
    test_chat_snapshot_round_trip_in_context()
    test_chat_http_client()
    test_chat_keeps_sessions_isolated()
    test_reset_only_clears_requested_session()
    print("ok")
