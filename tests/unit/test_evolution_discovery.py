import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.evolution_discovery import (  # noqa: E402
    fetch_recent_whatsapp_messages,
    name_query_matches,
)
from services.message_sources import IncomingMessage  # noqa: E402
from services.message_timeline import record_whatsapp_message  # noqa: E402

FIX = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "evolution"


def test_name_query_matches_tokens():
    assert name_query_matches("Pedro Unna", "pedro")
    assert name_query_matches("Pedro Unna", "pedro unna")
    assert name_query_matches("Pedro Unna", "unna")
    assert not name_query_matches("Leo", "pedro")
    assert not name_query_matches("a", "pedro unna")
    assert not name_query_matches("pedro unna", "a")


def test_record_group_participant_timeline():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        msg = IncomingMessage(
            id="g1",
            sender="120363412669107307@g.us",
            text="Reunião amanhã 10h",
            ts="2026-06-17T12:00:00+00:00",
            from_me=False,
            is_group=True,
            label="Pedro Unna",
            participant="5511999888777@s.whatsapp.net",
        )
        assert record_whatsapp_message(msg)
        part_dir = Path(tmp) / "contacts" / "5511999888777@s.whatsapp.net"
        assert part_dir.is_dir()
        timeline = (part_dir / "timeline.jsonl").read_text(encoding="utf-8")
        assert "Pedro Unna" in timeline or "Reunião" in timeline


def test_fetch_recent_with_mocks():
    from datetime import datetime, timezone

    contacts_raw = [
        {"id": "5511999888777@s.whatsapp.net", "pushName": "Pedro Unna"},
    ]
    chats_raw = [
        {"id": "5511999888777@s.whatsapp.net", "name": "Pedro Unna"},
    ]
    msgs_raw = json.loads((FIX / "find_messages.json").read_text(encoding="utf-8"))
    recent_ts = int(datetime.now(timezone.utc).timestamp()) - 3600
    for rec in msgs_raw["messages"]["records"]:
        rec["messageTimestamp"] = recent_ts

    class FakeClient:
        def find_contacts(self, *, limit=None):
            return contacts_raw

        def find_chats(self, *, limit=None):
            return chats_raw

        def find_messages(self, jid, *, limit=None):
            return msgs_raw

    with patch("services.evolution_discovery.EvolutionClient", FakeClient):
        rows = fetch_recent_whatsapp_messages(days=30, limit=10)
    assert rows
    assert any("reunião" in (r.get("preview") or "").lower() for r in rows)


if __name__ == "__main__":
    test_name_query_matches_tokens()
    test_record_group_participant_timeline()
    test_fetch_recent_with_mocks()
    print("ok")
