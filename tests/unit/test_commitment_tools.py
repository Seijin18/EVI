"""Unit tests for commitment review tools (SCN-CHAT-03/04)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Prefer the checkout this test file belongs to. Preferring /app meant that when
# the repo was mounted into a container whose image already had /app, the test
# silently exercised the STALE baked code — it was still asserting against the
# old `_tool_succeeded` after that function had been deleted.
_agent = Path(__file__).resolve().parents[2] / "agent"
if not (_agent / "main.py").is_file():
    _agent = Path("/app")
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


# --- SCN-CHAT-05: a failed booking must not mark the row scheduled -----------

_ROW_TASK = {
    "id": 7, "type": "task", "title": "Mandar relatório",
    "due_date": "2026-09-01", "event_date": None, "raw_text": "ctx",
}
_ROW_EVENT = {
    "id": 8, "type": "event", "title": "Reunião",
    "event_date": "2026-09-01", "event_time": "10:00", "raw_text": "ctx",
}


def _confirm(row, integration_response):
    """Drive confirm_commitments with a mocked Windmill response."""
    client = MagicMock()
    client.post.return_value = integration_response
    # Patch where the name is BOUND, not where it is defined: both tools do
    # `from integrations.factory import get_integration` at import time, so
    # patching the factory module leaves their reference untouched — and the
    # failure assertions would then pass vacuously against a dead Windmill.
    with patch("db.init_db"), patch(
        "db.list_pending_commitments", return_value=[row]
    ), patch("db.update_commitment_status") as upd, patch(
        "tools.calendar_tool.get_integration", return_value=client
    ), patch("tools.task_tool.get_integration", return_value=client):
        out = confirm_commitments.invoke(
            {"commitment_ids": [row["id"]], "confirmed_via": "chat"}
        )
    assert client.post.called, "the tool never reached the integration — test is vacuous"
    return out, upd


def test_error_detail_saying_criada_does_not_schedule():
    """The regression: `_tool_succeeded` matched the substring "criad".

    A Windmill error whose detail happens to contain "criada" used to be read as
    success, flipping the row to `scheduled` with no task behind it.
    """
    raw = (
        '{"status": "error", "action": "create_task", "http_status": 500,'
        ' "detail": "A tarefa nao pode ser criada: quota exceeded"}'
    )
    out, upd = _confirm(_ROW_TASK, raw)
    upd.assert_not_called()
    assert "failed" in out.lower() or "❌" in out


def test_error_detail_saying_created_does_not_schedule():
    raw = (
        '{"status": "error", "action": "schedule_event", "http_status": 403,'
        ' "detail": "event not created: insufficient permissions"}'
    )
    out, upd = _confirm(_ROW_EVENT, raw)
    upd.assert_not_called()


def test_transport_failure_does_not_schedule():
    """`Missing WINDMILL_*` carries no "failed" and used to slip through."""
    out, upd = _confirm(_ROW_EVENT, "Missing WINDMILL_WEBHOOK_CALENDAR")
    upd.assert_not_called()


def test_unparseable_response_does_not_schedule():
    out, upd = _confirm(_ROW_EVENT, "<html>502 Bad Gateway</html>")
    upd.assert_not_called()


def test_real_success_still_schedules():
    raw = (
        '{"status": "created", "action": "schedule_event", "event_id": "e1",'
        ' "html_link": "https://cal.google/e1"}'
    )
    out, upd = _confirm(_ROW_EVENT, raw)
    upd.assert_called_once()
    assert upd.call_args[0][1] == "scheduled"
    assert "cal.google/e1" in out or "criado" in out.lower()


def test_real_task_success_still_schedules():
    raw = '{"status": "created", "action": "create_task", "task_id": "t1"}'
    out, upd = _confirm(_ROW_TASK, raw)
    upd.assert_called_once()
