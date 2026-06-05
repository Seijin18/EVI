import json
import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.evolution_parser import parse_evolution_webhook  # noqa: E402

FIX = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "evolution"


def _load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_messages_array_fixture():
    msgs = parse_evolution_webhook(_load("messages_upsert.json"))
    assert len(msgs) == 1
    assert "Reunião" in msgs[0].text


def test_messages_v237_array_fixture():
    msgs = parse_evolution_webhook(_load("messages_upsert_v237.json"))
    assert len(msgs) == 1
    assert msgs[0].id == "evo237"


def test_single_message_envelope():
    body = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "real-id",
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"conversation": "salve amanhã reunião"},
            "messageTimestamp": 1717410900,
        },
    }
    msgs = parse_evolution_webhook(body)
    assert len(msgs) == 1
    assert msgs[0].id == "real-id"
    assert msgs[0].sender.endswith("@s.whatsapp.net")


if __name__ == "__main__":
    test_messages_array_fixture()
    test_messages_v237_array_fixture()
    test_single_message_envelope()
    print("ok")
