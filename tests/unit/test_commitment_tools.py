"""Unit tests for commitment review tools (SCN-CHAT-03/04)."""

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path("/app")
if not _agent.is_dir():
    _agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

# Stub db before commitment_tools imports psycopg2 transitively
_db = types.ModuleType("db")
_db.init_db = lambda: None
_db.list_pending_commitments = lambda limit=20: []
_db.update_commitment_status = lambda cid, status: True
sys.modules["db"] = _db

from tools.commitment_tools import (  # noqa: E402
    confirm_commitments,
    dismiss_commitments,
    list_pending_commitments,
)


def test_list_pending_empty():
    _db.list_pending_commitments = lambda limit=20: []
    out = list_pending_commitments.invoke({"limit": 5})
    assert out == "No pending commitments."


def test_list_pending_returns_json():
    _db.list_pending_commitments = lambda limit=20: [
        {
            "id": 1,
            "title": "Reunião",
            "type": "event",
            "priority": "work",
            "created_at": "2026-06-05",
        }
    ]
    out = list_pending_commitments.invoke({})
    data = json.loads(out)
    assert data[0]["title"] == "Reunião"


def test_confirm_event_calls_schedule():
    _db.list_pending_commitments = lambda limit=100: [
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
    _db.update_commitment_status = (
        lambda cid, status, confirmed_via="chat": updates.append((cid, status)) or True
    )
    with patch(
        "tools.calendar_tool.post_windmill",
        return_value='{"status":"created","action":"schedule_event"}',
    ) as sched:
        out = confirm_commitments.invoke({"commitment_ids": [2]})
    assert sched.called
    assert updates == [(2, "scheduled")]
    assert "#2:" in out


def test_confirm_task_calls_create_task():
    _db.list_pending_commitments = lambda limit=100: [
        {
            "id": 3,
            "type": "task",
            "title": "Comprar leite",
            "due_date": "2026-06-12",
            "raw_text": "lista",
        }
    ]
    updates = []
    _db.update_commitment_status = (
        lambda cid, status, confirmed_via="chat": updates.append((cid, status)) or True
    )
    with patch(
        "tools.task_tool.post_windmill",
        return_value='{"status":"created","action":"create_task"}',
    ) as task:
        confirm_commitments.invoke({"commitment_ids": [3]})
    assert task.called
    payload = task.call_args[0][1]
    assert payload["title"] == "Comprar leite"
    assert payload["due_date"] == "2026-06-12"
    assert updates == [(3, "scheduled")]


def test_dismiss_commitments():
    _db.update_commitment_status = lambda cid, status: cid == 5
    out = dismiss_commitments.invoke({"commitment_ids": [5, 9]})
    assert "Dismissed 1" in out


if __name__ == "__main__":
    test_list_pending_empty()
    test_list_pending_returns_json()
    test_confirm_event_calls_schedule()
    test_confirm_task_calls_create_task()
    test_dismiss_commitments()
    print("All commitment_tools tests passed")
