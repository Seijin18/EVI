"""SCN-API-03 — the endpoints outside /chat, especially the Evolution webhook.

The webhook is ~200 lines of routing (control JID vs ingest, echo guard, dedupe,
queueing, notify) and had no direct test. Its failure mode is silent: a message
is dropped and the only trace is a JSONL line.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from services.session_memory import reset_for_tests  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("EVI_API_KEY", "")
    monkeypatch.setenv("EVI_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "")
    main.app_state.graph = MagicMock()
    reset_for_tests()
    return TestClient(main.app)


def _upsert(jid: str, text: str, msg_id: str = "m1", from_me: bool = False):
    return {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": jid, "id": msg_id, "fromMe": from_me},
            "message": {"conversation": text},
            "messageTimestamp": 4102444800,  # far future: survives the age filter
            "pushName": "Fulano",
        },
    }


# --- basic surface ----------------------------------------------------------


def test_root_lists_services(client):
    body = client.get("/").json()
    assert body["status"] == "EVI is alive"
    assert "memory-only" in body["services"], "no DATABASE_URL means memory-only"


def test_tools_returns_the_registry(client):
    tools = client.get("/tools").json()["tools"]
    assert "schedule_event" in tools and "confirm_commitments" in tools
    assert "propose_dev_task_tool" not in tools, "dev bridge was removed"


def test_reset_is_scoped_and_reports_whether_it_existed(client):
    from services.session_memory import get_session_memory

    get_session_memory("keep").add("x")
    body = client.post("/reset", json={"session_id": "gone"}).json()
    assert body["session_id"] == "gone" and body["existed"] is False
    assert get_session_memory("keep").get_messages() == ["x"]


def test_note_writes_a_file(client, tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_NOTES_DIR", str(tmp_path / "notes"))
    r = client.post("/note", json={"title": "T", "content": "corpo", "tags": []})
    assert r.status_code == 200 and r.json()["status"] == "saved"


def test_run_task_rejects_an_unknown_tool(client):
    r = client.post("/run-task", json={"task": "nao_existe", "params": {}})
    assert r.status_code == 404


# --- evolution webhook ------------------------------------------------------


def _post_webhook(client, payload):
    with patch("services.contact_filesystem.ingest_commitment"), patch(
        "services.graph_sync.sync_commitment"
    ), patch("services.message_timeline.record_whatsapp_messages"):
        return client.post("/webhooks/evolution", json=payload)


def test_webhook_ingests_a_normal_message(client):
    r = _post_webhook(client, _upsert("5511888@s.whatsapp.net", "reunião dia 12 às 9h"))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["received"] == 1
    assert body["control"] == [], "not a control JID"


def test_webhook_skips_its_own_echo(client, monkeypatch):
    """Without this the bot answers itself in the control chat, forever."""
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "5511777@s.whatsapp.net")
    r = _post_webhook(client, _upsert("5511777@s.whatsapp.net", "[EVI] já respondi"))
    assert r.json()["control"] == []


def test_webhook_routes_a_control_jid_to_chat(client, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "5511777@s.whatsapp.net")
    with patch(
        "services.whatsapp_control.process_whatsapp_control_message",
        return_value={"ok": True, "response": "pong", "whatsapp_sent": True},
    ) as proc:
        r = _post_webhook(client, _upsert("5511777@s.whatsapp.net", "ping"))
    proc.assert_called_once()
    assert r.json()["control"][0]["response"] == "pong"


def test_webhook_deduplicates_a_replayed_control_message(client, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "5511777@s.whatsapp.net")
    monkeypatch.setenv("EVI_WHATSAPP_DEDUPE_IDS", "true")
    payload = _upsert("5511777@s.whatsapp.net", "ping", msg_id="dup-1")
    with patch(
        "services.whatsapp_control.process_whatsapp_control_message",
        return_value={"ok": True},
    ) as proc:
        _post_webhook(client, payload)
        _post_webhook(client, payload)
    assert proc.call_count == 1, "the same Evolution id must not be handled twice"


def test_webhook_drops_group_messages_by_default(client):
    r = _post_webhook(client, _upsert("1203630@g.us", "papo de grupo"))
    assert r.json()["ingested"] == 0
    assert r.json()["filter"]["skipped_group"] == 1


def test_webhook_drops_own_outgoing_messages(client):
    r = _post_webhook(client, _upsert("5511888@s.whatsapp.net", "eu mandei", from_me=True))
    assert r.json()["filter"]["skipped_from_me"] == 1


def test_webhook_tolerates_an_unknown_event(client):
    r = _post_webhook(client, {"event": "connection.update", "data": {}})
    assert r.status_code == 200 and r.json()["ingested"] == 0


def test_webhook_writes_a_jsonl_trace(client, tmp_path):
    _post_webhook(client, _upsert("1203630@g.us", "grupo"))
    log = tmp_path / "evolution_webhook.jsonl"
    assert log.is_file(), "every drop must leave a reason in the log"
    assert "filtered_out" in log.read_text()


# --- job endpoints ----------------------------------------------------------


def test_daily_summary_job(client):
    with patch("services.daily_summary.run_daily_summaries", return_value=3):
        assert client.post("/jobs/daily-summary").json() == {"ok": True, "written": 3}


def test_heartbeat_job(client):
    with patch("services.heartbeat.run_heartbeat", return_value={"ok": True, "ran": False}):
        assert client.post("/jobs/heartbeat").json()["ok"] is True
