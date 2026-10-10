"""SCN-DEBT-02 — per-conversation WhatsApp state recorded by the webhook."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from services import reply_debts  # noqa: E402
from services.message_sources import IncomingMessage  # noqa: E402
from services.session_memory import reset_for_tests  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "evolution"
DIRECT = "5511988887777@s.whatsapp.net"


class FakeDb:
    def __init__(self):
        self.inbound, self.outbound = [], []
        self.pending = []

    def init_db(self):
        pass

    def record_inbound(self, jid, ts, preview, msg_id):
        self.inbound.append((jid, ts, preview, msg_id))

    def record_outbound(self, jid, ts):
        self.outbound.append((jid, ts))

    def insert_pending_commitment(self, *a, **k):
        self.pending.append((a, k))
        return 1


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeDb()
    monkeypatch.setitem(sys.modules, "db", fake)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/fake")
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "")
    return fake


def _msg(jid=DIRECT, text="oi", from_me=False, ts="2026-06-03T10:00:00+00:00", mid="m1"):
    return IncomingMessage(
        id=mid, sender=jid, text=text, ts=ts, from_me=from_me,
        is_group="@g.us" in jid,
    )


def test_inbound_direct_records_preview_and_id(fake_db):
    assert reply_debts.track_conversation([_msg(text="x" * 300)]) == 1
    jid, ts, preview, mid = fake_db.inbound[0]
    assert jid == DIRECT and mid == "m1" and ts.year == 2026
    assert fake_db.outbound == []


def test_from_me_records_outbound_only(fake_db):
    reply_debts.track_conversation([_msg(from_me=True)])
    assert fake_db.outbound[0][0] == DIRECT
    assert fake_db.inbound == []


def test_group_control_and_echo_are_skipped(fake_db, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "5511777@s.whatsapp.net")
    n = reply_debts.track_conversation([
        _msg(jid="1203630@g.us"),
        _msg(jid="5511777@s.whatsapp.net"),
        _msg(from_me=True, text="[EVI] já respondi"),
    ])
    assert n == 0 and not fake_db.inbound and not fake_db.outbound


def test_missing_timestamp_falls_back_to_now(fake_db):
    reply_debts.track_conversation([_msg(ts="")])
    assert fake_db.inbound[0][1].tzinfo is not None


def test_no_database_url_is_a_noop(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert reply_debts.track_conversation([_msg()]) == 0


def test_db_failure_never_raises(fake_db):
    def boom(*a, **k):
        raise RuntimeError("db down")

    fake_db.record_inbound = boom
    assert reply_debts.track_conversation([_msg()]) == 0


# --- webhook ---------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path, fake_db):
    monkeypatch.setenv("EVI_API_KEY", "")
    monkeypatch.setenv("EVI_LOG_DIR", str(tmp_path))
    main.app_state.graph = MagicMock()
    reset_for_tests()
    return TestClient(main.app)


def _post(client, payload):
    with patch("services.contact_filesystem.ingest_commitment"), patch(
        "services.graph_sync.sync_commitment"
    ), patch("services.message_timeline.record_whatsapp_messages"):
        return client.post("/webhooks/evolution", json=payload)


def test_scn_debt_02_from_me_updates_last_out_without_commitment(client, fake_db):
    payload = json.loads((FIXTURES / "messages_upsert_from_me.json").read_text())
    r = _post(client, payload)
    assert r.status_code == 200
    assert [o[0] for o in fake_db.outbound] == [DIRECT]
    assert fake_db.inbound == []
    assert fake_db.pending == [], "fromMe never reaches extraction"
    assert r.json()["ingested"] == 0


def test_scn_debt_02_group_updates_no_state(client, fake_db):
    payload = json.loads((FIXTURES / "messages_upsert_from_me.json").read_text())
    payload["data"]["messages"][0]["key"]["remoteJid"] = "1203630@g.us"
    _post(client, payload)
    assert not fake_db.outbound and not fake_db.inbound


def test_control_chat_updates_no_state(client, fake_db, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", DIRECT)
    payload = json.loads((FIXTURES / "messages_upsert_from_me.json").read_text())
    with patch(
        "services.whatsapp_control.process_whatsapp_control_message",
        return_value={"ok": True},
    ):
        _post(client, payload)
    assert not fake_db.outbound and not fake_db.inbound


def test_inbound_webhook_records_inbound(client, fake_db):
    payload = json.loads((FIXTURES / "messages_upsert.json").read_text())
    _post(client, payload)
    assert fake_db.inbound and fake_db.inbound[0][3] == "evo001"


def test_tracking_failure_does_not_break_webhook(client, fake_db):
    with patch("services.reply_debts.track_conversation", side_effect=RuntimeError("x")):
        payload = json.loads((FIXTURES / "messages_upsert.json").read_text())
        assert _post(client, payload).status_code == 200
