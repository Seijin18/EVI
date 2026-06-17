import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.evolution_parser import parse_evolution_message_list  # noqa: E402
from services.whatsapp_backfill import backfill_contact_messages  # noqa: E402

FIX = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "evolution"


def test_parse_find_messages_fixture():
    raw = json.loads((FIX / "find_messages.json").read_text(encoding="utf-8"))
    msgs = parse_evolution_message_list(raw, remote_jid="5516992657231@s.whatsapp.net")
    assert len(msgs) == 2
    assert msgs[0].id == "hist001"
    assert "reunião" in msgs[0].text.lower()
    assert msgs[1].from_me is True


def test_backfill_appends_timeline():
    raw = json.loads((FIX / "find_messages.json").read_text(encoding="utf-8"))
    recent_ts = int(datetime.now(timezone.utc).timestamp()) - 3600

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        os.environ["EVI_BACKFILL_INCLUDE_FROM_ME"] = "true"
        jid = "5516992657231@s.whatsapp.net"

        records = raw["messages"]["records"]
        records[0]["messageTimestamp"] = recent_ts
        records[1]["messageTimestamp"] = recent_ts + 60

        class FakeClient:
            def find_messages(self, _jid, *, limit=None):
                return raw

        with patch("services.whatsapp_backfill.EvolutionClient", FakeClient):
            result = backfill_contact_messages(jid, label="Leozao", days=30)

        assert result.fetched == 2
        assert result.appended == 2
        timeline = (
            Path(tmp) / "contacts" / jid / "timeline.jsonl"
        ).read_text(encoding="utf-8")
        assert "hist001" in timeline
        assert "[Leozao]" in timeline
        assert "[eu]" in timeline


def test_backfill_dedupes():
    raw = json.loads((FIX / "find_messages.json").read_text(encoding="utf-8"))
    recent_ts = int(datetime.now(timezone.utc).timestamp()) - 3600

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVI_CONTACT_MEMORY_DIR"] = tmp
        jid = "5516992657231@s.whatsapp.net"
        records = raw["messages"]["records"]
        records[0]["messageTimestamp"] = recent_ts
        records[1]["messageTimestamp"] = recent_ts + 60

        class FakeClient:
            def find_messages(self, _jid, *, limit=None):
                return raw

        with patch("services.whatsapp_backfill.EvolutionClient", FakeClient):
            first = backfill_contact_messages(jid, label="Leozao", days=30)
            second = backfill_contact_messages(jid, label="Leozao", days=30)

        assert first.appended == 2
        assert second.appended == 0
        assert second.skipped_dup == 2


if __name__ == "__main__":
    test_parse_find_messages_fixture()
    test_backfill_appends_timeline()
    test_backfill_dedupes()
    print("ok")
