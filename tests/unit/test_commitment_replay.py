import json
import os
import sys
import tempfile
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.commitment_replay import replay_commitments_from_evolution_log  # noqa: E402
from services.message_sources import IncomingMessage  # noqa: E402
from services.whatsapp_processor import extract_commitment, _resolve_time  # noqa: E402


def test_resolve_time_as_17():
    assert _resolve_time("Marcar vôlei dia 22/06, às 17") == "17:00"
    assert _resolve_time("às 17h30") == "17:30"


def test_replay_queues_volleyball(tmp_path, monkeypatch):
    log = tmp_path / "evolution_webhook.jsonl"
    jid = "5511959875299@s.whatsapp.net"
    log.write_text(
        json.dumps(
            {
                "step": "ingest",
                "source_id": "3AFAAB5128F920FF0ECF",
                "sender": jid,
                "from_me": False,
                "raw_preview": "Marcar para Jogar vôlei, segunda feira dia 22/06, às 17",
                "message_ts": "2026-06-17T12:40:02+00:00",
                "label": "PNFagundes",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    queued: list[int] = []

    def fake_insert(**kwargs):
        queued.append(1)
        return 99

    monkeypatch.setenv("EVI_LOG_DIR", str(tmp_path))
    monkeypatch.setattr("db.init_db", lambda: None)
    monkeypatch.setattr("db.insert_pending_commitment", fake_insert)

    result = replay_commitments_from_evolution_log(
        jid=jid, days=14, log_path=log
    )
    assert result.extracted >= 1
    assert result.queued == 1


def test_extract_volleyball_message():
    msg = IncomingMessage(
        id="x",
        sender="5511959875299@s.whatsapp.net",
        text="Marcar para Jogar vôlei, segunda feira dia 22/06, às 17",
        ts="2026-06-17T12:40:02+00:00",
    )
    c = extract_commitment(msg)
    assert c is not None
    assert c.date == "2026-06-22"
    assert c.time == "17:00"
    assert c.title == "Vôlei"


if __name__ == "__main__":
    test_resolve_time_as_17()
    test_extract_volleyball_message()
    print("ok")
