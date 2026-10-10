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


def _audio_body(jid="5511@s.whatsapp.net", **audio):
    return {
        "event": "messages.upsert",
        "data": {
            "key": {"id": "AUD1", "remoteJid": jid, "fromMe": False},
            "messageTimestamp": 1767225600,
            "message": {"audioMessage": {"mimetype": "audio/ogg; codecs=opus", "seconds": 7, **audio}},
        },
    }


def test_audio_message_is_recognised():
    msgs = parse_evolution_webhook(_audio_body())
    assert len(msgs) == 1
    m = msgs[0]
    assert m.kind == "audio"
    assert m.text == ""
    assert m.audio_seconds == 7
    assert m.audio_mime == "audio/ogg"
    assert m.media_key["id"] == "AUD1"


def test_audio_mime_defaults_to_ogg():
    body = _audio_body()
    del body["data"]["message"]["audioMessage"]["mimetype"]
    assert parse_evolution_webhook(body)[0].audio_mime == "audio/ogg"


def test_text_message_kind_is_text():
    msgs = parse_evolution_webhook(_load("messages_upsert.json"))
    assert msgs[0].kind == "text"
    assert msgs[0].media_key is None
