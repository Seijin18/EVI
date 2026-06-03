from pathlib import Path

from services.message_sources import IncomingMessage
from services.whatsapp_processor import extract_commitment, process_fixture_file

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


if __name__ == "__main__":
    test_extract_meeting_tomorrow()
    test_extract_task_friday()
    test_skip_acknowledgement()
    test_fixture_pipeline_matches_golden()
    print("All whatsapp unit tests passed")
