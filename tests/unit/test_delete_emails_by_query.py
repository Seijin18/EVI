"""Unit tests for delete_emails_by_query tool (first call is a dry-run preview)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from tools.email_tool import delete_emails_by_query  # noqa: E402


def test_delete_by_query_never_deletes_without_confirmation():
    mock_client = MagicMock()
    mock_client.post.return_value = (
        '{"status":"ok","count":2,"messages":'
        '[{"id":"a","subject":"s","from":"f"},{"id":"b","subject":"t","from":"f"}]}'
    )
    with patch("tools.email_tool.get_integration", return_value=mock_client):
        out = delete_emails_by_query.invoke({"q": "from:aliexpress"})
    # no chat turn in progress: refuses to even stage a deletion
    assert "fora de uma conversa" in out
    assert [c[0][0] for c in mock_client.post.call_args_list] == ["search_emails"]
