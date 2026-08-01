"""Unit tests for commitment review tools (SCN-CHAT-03/04)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path("/app")
if not _agent.is_dir():
    _agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from tools.commitment_tools import (  # noqa: E402
    confirm_commitments,
    dismiss_commitments,
    list_pending_commitments,
)


def test_list_pending_empty():
    with patch("db.init_db"), patch(
        "db.list_pending_commitments", return_value=[]
    ):
        out = list_pending_commitments.invoke({"limit": 5})
    assert out == "Nenhum compromisso pendente."


def test_list_pending_returns_digest():
    rows = [
        {
            "id": 1,
            "title": "Reunião",
            "type": "event",
            "priority": "work",
            "created_at": "2026-06-05",
        }
    ]
    with patch("db.init_db"), patch(
        "db.list_pending_commitments", return_value=rows
    ):
        out = list_pending_commitments.invoke({})
    assert "Reunião" in out
    assert "[1]" in out


def test_confirm_event_calls_schedule():
    rows = [
        {
            "id": 2,
            "type": "event",
            "title": "Call",
            "event_date": "2026-06-10",
            "event_time": "14:00",
            "raw_text": "sync",
        }
    ]
    updates = []
    mock_client = MagicMock()
    mock_client.post.return_value = '{"status":"created","action":"schedule_event"}'
    with patch("db.init_db"), patch(
        "db.list_pending_commitments", return_value=rows
    ), patch(
        "db.update_commitment_status",
        side_effect=lambda cid, status, confirmed_via="chat": updates.append(
            (cid, status)
        )
        or True,
    ), patch("tools.calendar_tool.get_integration", return_value=mock_client):
        out = confirm_commitments.invoke({"commitment_ids": [2]})
    assert mock_client.post.called
    assert updates == [(2, "scheduled")]
    assert "#2:" in out


def test_confirm_task_calls_create_task():
    rows = [
        {
            "id": 3,
            "type": "task",
            "title": "Comprar leite",
            "due_date": "2026-06-12",
            "raw_text": "lista",
        }
    ]
    updates = []
    mock_task_client = MagicMock()
    mock_task_client.post.return_value = '{"status":"created","action":"create_task"}'
    with patch("db.init_db"), patch(
        "db.list_pending_commitments", return_value=rows
    ), patch(
        "db.update_commitment_status",
        side_effect=lambda cid, status, confirmed_via="chat": updates.append(
            (cid, status)
        )
        or True,
    ), patch("tools.task_tool.get_integration", return_value=mock_task_client):
        confirm_commitments.invoke({"commitment_ids": [3]})
    assert mock_task_client.post.called
    payload = mock_task_client.post.call_args[0][1]
    assert payload["title"] == "Comprar leite"
    assert payload["due_date"] == "2026-06-12"
    assert updates == [(3, "scheduled")]


def test_dismiss_commitments():
    with patch("db.init_db"), patch(
        "db.update_commitment_status", side_effect=lambda cid, status: cid == 5
    ):
        out = dismiss_commitments.invoke({"commitment_ids": [5, 9]})
    assert "Dismissed 1" in out


if __name__ == "__main__":
    test_list_pending_empty()
    test_list_pending_returns_digest()
    test_confirm_event_calls_schedule()
    test_confirm_task_calls_create_task()
    test_dismiss_commitments()
    print("All commitment_tools tests passed")
