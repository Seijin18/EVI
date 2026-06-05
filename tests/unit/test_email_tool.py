"""Unit tests for summarize_inbox (SCN-EMAIL-03)."""

import sys
import types
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

_lc_tools = types.ModuleType("langchain_core.tools")


def _tool(func):
    class _Wrapped:
        def invoke(self, input_dict):
            return func(**input_dict)

    return _Wrapped()


_lc_tools.tool = _tool
sys.modules.setdefault("langchain_core", types.ModuleType("langchain_core"))
sys.modules["langchain_core.tools"] = _lc_tools

from tools.email_tool import summarize_inbox  # noqa: E402


def test_summarize_inbox_success():
    mock_result = '{"status":"ok","summary":"2 unread threads","count":2}'
    with patch("tools.email_tool.post_windmill", return_value=mock_result):
        out = summarize_inbox.invoke({"max_messages": 5})
    assert "summary" in out.lower()
    assert "failed" not in out.lower()


def test_summarize_inbox_failure():
    with patch("tools.email_tool.post_windmill", return_value="Windmill job failed: 401"):
        out = summarize_inbox.invoke({})
    assert "Failed" in out


if __name__ == "__main__":
    test_summarize_inbox_success()
    test_summarize_inbox_failure()
    print("ok")
