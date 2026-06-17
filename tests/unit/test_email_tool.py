"""Unit tests for summarize_inbox (SCN-EMAIL-03)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from tools.email_tool import summarize_inbox  # noqa: E402


def test_summarize_inbox_success():
    mock_result = (
        '{"status":"ok","summary":"x","count":1,'
        '"messages":[{"id":"m1","subject":"Hi","from":"a@b.com"}]}'
    )
    mock_client = MagicMock()
    mock_client.post.return_value = mock_result
    with patch("tools.email_tool.get_integration", return_value=mock_client):
        out = summarize_inbox.invoke({"max_messages": 5})
    assert "Caixa de entrada" in out
    assert "Hi" in out
    assert "failed" not in out.lower()


def test_summarize_inbox_failure():
    mock_client = MagicMock()
    mock_client.post.return_value = "Windmill job failed: 401"
    with patch("tools.email_tool.get_integration", return_value=mock_client):
        out = summarize_inbox.invoke({})
    assert "Gmail" in out or "Não foi possível" in out


if __name__ == "__main__":
    test_summarize_inbox_success()
    test_summarize_inbox_failure()
    print("ok")
