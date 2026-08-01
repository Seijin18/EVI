"""Unit tests for session tool snapshots."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.session_context import (  # noqa: E402
    persist_tool_snapshots,
    summarize_tool_calls,
)


def test_summarize_tool_calls():
    ai = MagicMock(type="ai", tool_calls=[{"name": "summarize_inbox"}])
    tool = MagicMock(type="tool", content='{"status":"ok"}')
    tool.name = "summarize_inbox"  # "name" is a reserved MagicMock() kwarg
    summary = summarize_tool_calls([ai, tool])
    assert any(
        s.get("tool") == "summarize_inbox" and s.get("kind") == "result"
        for s in summary
    )


def test_persist_tool_snapshots_parses_json():
    tool = MagicMock(
        type="tool",
        content=json.dumps({"status": "ok", "messages": [{"id": "abc"}]}),
    )
    tool.name = "summarize_inbox"  # "name" is a reserved MagicMock() kwarg
    with patch("db.init_db"), patch("db.save_tool_snapshot") as save:
        saved = persist_tool_snapshots("telegram-1", [tool])
    assert len(saved) == 1
    save.assert_called_once()
    args = save.call_args[0]
    assert args[0] == "telegram-1"
    assert args[1] == "summarize_inbox"
