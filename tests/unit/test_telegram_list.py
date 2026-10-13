import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))


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
    with patch("tools.commitment_tools.pending_rows", return_value=[]):
        out = try_direct_list("Listar compromissos pendentes")
    assert out and "Nenhum" in out


_ROWS = [
    {"id": 31, "title": "Mandar a modelagem", "type": "promise", "source_label": "Eliana",
     "event_date": "2026-10-16"},
    {"id": 33, "title": "Ligar para a clínica", "type": "task", "source_chat": "999000111@lid"},
]


def test_scn_ux_02_direct_list_is_clean_but_carries_marked_model_text():
    from services.untrusted import has_marker

    with patch("tools.commitment_tools.pending_rows", return_value=_ROWS):
        out = try_direct_list("Listar compromissos pendentes")
    assert not has_marker(out) and "@lid" not in out and "[31]" not in out
    assert out.splitlines()[1].startswith("31. Eliana · Mandar a modelagem")
    assert has_marker(out.model)  # what the session/LLM remembers


def test_scn_ux_02_tool_output_for_the_llm_stays_marked():
    from services.untrusted import has_marker
    from tools.commitment_tools import list_pending_commitments

    with patch("tools.commitment_tools.pending_rows", return_value=_ROWS):
        assert has_marker(list_pending_commitments.invoke({"limit": 20}))


if __name__ == "__main__":
    test_wants_list_agendamentos()
    test_direct_list_calls_calendar_tool()
    test_direct_list_pending()
    print("ok")
