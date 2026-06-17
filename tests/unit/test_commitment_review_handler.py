"""Unit tests for services/commitment_review/handler.py (try_direct_review)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.commitment_review.handler import try_direct_review  # noqa: E402


def test_confirm_ids():
    mock = MagicMock()
    mock.invoke.return_value = "Agendado: #1"
    with patch("tools.commitment_tools.confirm_commitments", mock):
        result = try_direct_review("confirmar 1,2", confirmed_via="test")
    mock.invoke.assert_called_once_with({"commitment_ids": [1, 2], "confirmed_via": "test"})
    assert result == "Agendado: #1"


def test_agendar_alias():
    mock = MagicMock()
    mock.invoke.return_value = "ok"
    with patch("tools.commitment_tools.confirm_commitments", mock):
        result = try_direct_review("agendar 3")
    mock.invoke.assert_called_once_with({"commitment_ids": [3], "confirmed_via": "chat"})


def test_dismiss_ids():
    mock = MagicMock()
    mock.invoke.return_value = "Dismissed 1"
    with patch("tools.commitment_tools.dismiss_commitments", mock):
        result = try_direct_review("dispensar 1")
    mock.invoke.assert_called_once_with({"commitment_ids": [1]})
    assert "Dismissed" in result


def test_list_pending():
    mock = MagicMock()
    mock.invoke.return_value = "EVI: compromissos pendentes"
    with patch("tools.commitment_tools.list_pending_commitments", mock):
        result = try_direct_review("listar compromissos pendentes")
    mock.invoke.assert_called_once()
    assert result is not None


def test_revisar_compromissos_uses_pending_not_calendar():
    pending = MagicMock()
    pending.invoke.return_value = "EVI: compromissos pendentes"
    calendar = MagicMock()
    with patch("tools.commitment_tools.list_pending_commitments", pending):
        with patch("tools.calendar_tool.list_calendar_events", calendar):
            result = try_direct_review("Revisar compromissos")
    pending.invoke.assert_called_once()
    calendar.invoke.assert_not_called()
    assert result is not None


def test_list_today():
    mock = MagicMock()
    mock.invoke.return_value = "Nenhum hoje."
    with patch("tools.commitment_tools.list_scheduled_today", mock):
        result = try_direct_review("hoje")
    mock.invoke.assert_called_once()


def test_list_calendar():
    mock = MagicMock()
    mock.invoke.return_value = "Próximos eventos (0):"
    with patch("tools.calendar_tool.list_calendar_events", mock):
        result = try_direct_review("listar agendamentos do calendário")
    mock.invoke.assert_called_once()


def test_no_match_returns_none():
    result = try_direct_review("tudo bem?")
    assert result is None


def test_confirm_with_ids_hint():
    """confirmar N,M com IDs inválidos após keyword returns hint."""
    result = try_direct_review("confirmar abc")
    assert result is None or "id" in (result or "").lower()


def test_no_trailing_ids_returns_none():
    """bare 'confirmar' without ids doesn't match and returns None."""
    result = try_direct_review("confirmar")
    assert result is None


def test_confirm_all_calls_confirm_with_all_ids():
    list_mock = MagicMock(return_value=[{"id": 1}, {"id": 2}])
    confirm_mock = MagicMock()
    confirm_mock.invoke.return_value = "Agendados: 1, 2"
    with patch("db.list_pending_commitments", list_mock):
        with patch("db.init_db"):
            with patch("tools.commitment_tools.confirm_commitments", confirm_mock):
                result = try_direct_review("confirmar tudo")
    confirm_mock.invoke.assert_called_once_with({"commitment_ids": [1, 2], "confirmed_via": "chat"})
    assert "Agendados" in result


def test_confirm_all_no_pending():
    with patch("db.list_pending_commitments", MagicMock(return_value=[])):
        with patch("db.init_db"):
            result = try_direct_review("agendar todos")
    assert "Nenhum" in result


def test_dismiss_all_calls_dismiss_with_all_ids():
    list_mock = MagicMock(return_value=[{"id": 3}])
    dismiss_mock = MagicMock()
    dismiss_mock.invoke.return_value = "Dispensados: 3"
    with patch("db.list_pending_commitments", list_mock):
        with patch("db.init_db"):
            with patch("tools.commitment_tools.dismiss_commitments", dismiss_mock):
                result = try_direct_review("dispensar tudo")
    dismiss_mock.invoke.assert_called_once_with({"commitment_ids": [3]})
    assert "Dispensados" in result


if __name__ == "__main__":
    test_confirm_ids()
    test_agendar_alias()
    test_dismiss_ids()
    test_list_pending()
    test_list_today()
    test_list_calendar()
    test_no_match_returns_none()
    test_no_trailing_ids_returns_none()
    print("ok")
