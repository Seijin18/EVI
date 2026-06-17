from pathlib import Path

from services.message_sources import IncomingMessage
from services.whatsapp_processor import _resolve_date, _resolve_time, extract_commitment, process_fixture_file

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "whatsapp" / "messages.jsonl"
GOLDEN = ROOT / "tests" / "golden" / "whatsapp_commitments.json"


def test_extract_meeting_tomorrow():
    msg = IncomingMessage(
        id="w001",
        sender="Maria",
        text="Reunião com o cliente amanhã às 14h na sala 3",
        ts="2026-06-03T09:15:00",
    )
    c = extract_commitment(msg)
    assert c is not None
    assert c.type == "event"
    assert c.date == "2026-06-04"
    assert c.time == "14:00"


def test_extract_task_friday():
    msg = IncomingMessage(
        id="w002",
        sender="João",
        text="Lembre de enviar o relatório até sexta",
        ts="2026-06-03T10:00:00",
    )
    c = extract_commitment(msg)
    assert c is not None
    assert c.type == "task"
    assert c.due == "2026-06-05"


def test_skip_acknowledgement():
    msg = IncomingMessage(
        id="w004", sender="Maria", text="Ok, combinado", ts="2026-06-03T09:20:00"
    )
    assert extract_commitment(msg) is None


def test_fixture_pipeline_matches_golden():
    assert process_fixture_file(FIXTURE, GOLDEN, log_path=None, verbose=False)


def _ref():
    from datetime import datetime
    return datetime(2026, 6, 3, 9, 0, 0)  # Wednesday


def test_resolve_date_hoje():
    assert _resolve_date("almoço hoje às 12h", _ref()) == "2026-06-03"


def test_resolve_date_amanha():
    assert _resolve_date("reunião amanhã", _ref()) == "2026-06-04"


def test_resolve_date_proxima_semana():
    result = _resolve_date("próxima semana temos reunião", _ref())
    # next Monday from Wednesday 2026-06-03
    assert result == "2026-06-08"


def test_resolve_date_weekday_terca():
    result = _resolve_date("terça-feira às 10h", _ref())
    assert result == "2026-06-09"  # next Tuesday


def test_resolve_date_weekday_quinta():
    result = _resolve_date("quinta às 15h", _ref())
    assert result == "2026-06-04"  # next Thursday


def test_resolve_date_explicit_month():
    result = _resolve_date("dia 15 de julho", _ref())
    assert result == "2026-07-15"


def test_resolve_time_explicit():
    assert _resolve_time("reunião às 10h30") == "10:30"


def test_resolve_time_period_manha():
    assert _resolve_time("reunião de manhã") == "09:00"


def test_resolve_time_period_tarde():
    assert _resolve_time("encontro à tarde") == "14:00"


def test_resolve_time_period_noite():
    assert _resolve_time("jantar à noite") == "20:00"


def test_extract_meeting_hoje():
    msg = IncomingMessage(
        id="w010",
        sender="Ana",
        text="Reunião com diretor hoje às 15h",
        ts="2026-06-03T09:00:00",
    )
    c = extract_commitment(msg)
    assert c is not None
    assert c.date == "2026-06-03"
    assert c.time == "15:00"


def test_extract_dinner_proxima_semana():
    msg = IncomingMessage(
        id="w011",
        sender="Carlos",
        text="Jantar com clientes próxima semana",
        ts="2026-06-03T09:00:00",
    )
    c = extract_commitment(msg)
    assert c is not None
    assert c.date == "2026-06-08"


def test_extract_volleyball_segunda():
    msg = IncomingMessage(
        id="w012",
        sender="5511959875299@s.whatsapp.net",
        text="Vamos marcar um vôlei para segunda feira\n\nQual horário vc prefere?",
        ts="2026-06-17T12:39:10+00:00",
        label="PNFagundes",
    )
    c = extract_commitment(msg)
    assert c is not None
    assert c.type == "event"
    assert c.title == "Vôlei"
    assert c.date == "2026-06-22"

    msg2 = IncomingMessage(
        id="w013",
        sender="5511959875299@s.whatsapp.net",
        text="Marcar para Jogar vôlei, segunda feira dia 22/06, às 17",
        ts="2026-06-17T12:40:02+00:00",
    )
    c2 = extract_commitment(msg2)
    assert c2 is not None
    assert c2.date == "2026-06-22"
    assert c2.time == "17:00"


if __name__ == "__main__":
    test_extract_meeting_tomorrow()
    test_extract_task_friday()
    test_skip_acknowledgement()
    test_fixture_pipeline_matches_golden()
    test_resolve_date_hoje()
    test_resolve_date_amanha()
    test_resolve_date_proxima_semana()
    test_resolve_date_weekday_terca()
    test_resolve_date_weekday_quinta()
    test_resolve_date_explicit_month()
    test_resolve_time_explicit()
    test_resolve_time_period_manha()
    test_resolve_time_period_tarde()
    test_resolve_time_period_noite()
    test_extract_meeting_hoje()
    test_extract_dinner_proxima_semana()
    print("All whatsapp unit tests passed")
