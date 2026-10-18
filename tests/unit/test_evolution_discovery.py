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


def test_pretty_phone_and_label_resolution_never_returns_raw_jid():
    from services.evolution_discovery import pretty_phone, resolve_chat_label

    assert pretty_phone("5511955550209@s.whatsapp.net") == "+55 11 95555-0209"
    assert pretty_phone("123@lid") == ""
    registry = {"5511955550444@s.whatsapp.net": {"display_name": "Carla Exemplo", "whatsapp_label": "Eli"}}
    # address-book name wins; the phone is kept for disambiguation
    assert resolve_chat_label("5511955550444@s.whatsapp.net", "5511955550444", registry) == (
        "Carla Exemplo",
        "+55 11 95555-0444",
    )
    # LID chat: the phone comes from remoteJidAlt
    assert resolve_chat_label("999@lid", "999", registry, alt_jid="5511955550444@s.whatsapp.net")[0] == "Carla Exemplo"
    # unknown contact: formatted phone, then profile name, never the JID
    assert resolve_chat_label("5511999999999@s.whatsapp.net", "5511999999999@s.whatsapp.net", {})[0] == "+55 11 99999-9999"
    assert resolve_chat_label("5511999999999@s.whatsapp.net", "Zeca", {})[0] == "Zeca"
    assert resolve_chat_label("888@lid", "888", {})[0] == "Contato sem nome"
    assert resolve_chat_label("1203@g.us", "1203@g.us", {})[0] == "Grupo sem nome"


def test_fetch_recent_parallel_and_budget():
    import threading
    import time

    release = threading.Event()
    jids = [f"55119000000{i:02d}@s.whatsapp.net" for i in range(4)]

    class Fake:
        def find_chats(self, *, limit=None):
            return [{"id": j, "name": j[:6]} for j in jids]

        def find_messages(self, jid, *, limit=None):
            if jid == jids[0]:
                release.wait(5)
                return None
            return {"messages": {"records": [{
                "key": {"remoteJid": jid, "id": "i" + jid, "fromMe": False},
                "message": {"conversation": "olá " + jid[-4:]},
                "messageTimestamp": int(time.time()) - 60}]}}

    status: dict = {}
    t0 = time.monotonic()
    with patch("services.evolution_discovery.EvolutionClient", Fake), patch(
        "services.evolution_discovery._registry_map", return_value={}
    ):
        rows = fetch_recent_whatsapp_messages(days=1, limit=10, budget_sec=0.5, status=status)
    release.set()
    assert time.monotonic() - t0 < 3
    assert status == {"incomplete": True}
    assert {r["chat_jid"] for r in rows} == set(jids[1:])
