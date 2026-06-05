import sys
import types
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

_lc_tools = types.ModuleType("langchain_core.tools")
_lc_tools.tool = lambda f: f
sys.modules.setdefault("langchain_core", types.ModuleType("langchain_core"))
sys.modules["langchain_core.tools"] = _lc_tools

from services.telegram_list import wants_list, try_direct_list  # noqa: E402


def test_wants_list_agendamentos():
    assert wants_list("Quero revisar os agendamentos de hoje")
    assert wants_list("Liste meus compromissos do calendário")
    assert not wants_list("Agende almoço hoje às 11h")


def test_direct_list_calls_calendar_tool():
    with patch("tools.calendar_tool.list_calendar_events") as mock:
        mock.invoke.return_value = "Próximos eventos (1):\n• 05/06 11:00 — almoço"
        out = try_direct_list("Mostre os eventos da agenda")
    assert out and "almoço" in out
    mock.invoke.assert_called_once()


def test_direct_list_pending():
    with patch("tools.commitment_tools.list_pending_commitments") as mock:
        mock.invoke.return_value = "No pending commitments."
        out = try_direct_list("Listar compromissos pendentes")
    assert out and "Nenhum" in out


if __name__ == "__main__":
    test_wants_list_agendamentos()
    test_direct_list_calls_calendar_tool()
    test_direct_list_pending()
    print("ok")
