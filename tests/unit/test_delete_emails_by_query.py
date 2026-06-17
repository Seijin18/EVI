"""Unit tests for delete_emails_by_query tool."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from tools.email_tool import delete_emails_by_query  # noqa: E402


def test_delete_by_query_success():
    mock_result = '{"status":"ok","deleted":2,"q":"from:aliexpress"}'
    mock_client = MagicMock()
    mock_client.post.return_value = mock_result
    with patch("tools.email_tool.get_integration", return_value=mock_client):
        out = delete_emails_by_query.invoke({"q": "from:aliexpress"})
    assert "2 email" in out
    mock_client.post.assert_called_once()
    assert mock_client.post.call_args[0][0] == "delete_emails_by_query"
