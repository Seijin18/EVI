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

from services.telegram_schedule import (  # noqa: E402
    _parse_title,
    _parse_when,
    wants_schedule,
)


def test_wants_schedule():
    assert wants_schedule("Agende para mim um almoço hoje às 11h")
    assert not wants_schedule("qual a previsão do tempo?")


def test_parse_when_hoje():
    date_s, start, end = _parse_when("hoje às 11:45")
    assert len(date_s) == 10
    assert start == "11:45"
    assert end == "12:45"


def test_parse_title_quoted():
    assert "pedir almoço" in _parse_title('evento "pedir almoço" hoje')
    assert _parse_title('com o nome \u201cpedir almoço\u201d hoje') == "pedir almoço"


def test_direct_schedule_calls_tool():
    from services.telegram_schedule import try_direct_schedule

    with patch("tools.calendar_tool.schedule_event") as mock:
        mock.invoke.return_value = "Evento 'almoco' criado.\nLink: https://calendar.google.com/x"
        out = try_direct_schedule("Agende almoço hoje às 11h")
    assert out and "Link:" in out
    mock.invoke.assert_called_once()


if __name__ == "__main__":
    test_wants_schedule()
    test_parse_when_hoje()
    test_parse_title_quoted()
    test_direct_schedule_calls_tool()
    print("ok")
