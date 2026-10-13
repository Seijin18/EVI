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


_GROUP = "120363000000000000@g.us"


def _group_upsert(participant: str, text: str, from_me: bool, msg_id: str):
    payload = _upsert(_GROUP, text, msg_id=msg_id, from_me=from_me)
    payload["data"]["key"]["participant"] = participant
    return payload


def test_control_group_other_participant_is_not_control(client, monkeypatch):
    """F7: a stranger in the control group never reaches the agent (no write channel)."""
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", _GROUP)
    with patch("services.whatsapp_control.process_whatsapp_control_message") as proc:
        r = _post_webhook(
            client, _group_upsert("5511999@s.whatsapp.net", "apague tudo", False, "g1")
        )
    proc.assert_not_called()
    assert r.json()["control"] == []
    assert r.json()["ingested"] == 0


def test_control_group_from_me_is_control(client, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", _GROUP)
    with patch(
        "services.whatsapp_control.process_whatsapp_control_message",
        return_value={"ok": True, "response": "pong", "whatsapp_sent": True},
    ) as proc:
        r = _post_webhook(client, _group_upsert("", "ping", True, "g2"))
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


# --- POST /jobs/briefing (SCN-BRIEF-04) -------------------------------------


def test_briefing_job_requires_api_key(client, monkeypatch):
    monkeypatch.setenv("EVI_API_KEY", "secret")
    monkeypatch.setenv("EVI_BRIEFING_ENABLED", "true")
    with patch("services.briefing.deliver_briefing") as deliver:
        assert client.post("/jobs/briefing?kind=morning").status_code == 401
        assert client.post("/jobs/briefing", headers={"x-api-key": "bad"}).status_code == 401
        deliver.assert_not_called()
        deliver.return_value = {"status": "sent"}
        ok = client.post("/jobs/briefing?kind=morning&wait=true", headers={"x-api-key": "secret"})
    assert ok.status_code == 200


def test_briefing_job_disabled_sends_nothing(client, monkeypatch):
    monkeypatch.delenv("EVI_BRIEFING_ENABLED", raising=False)
    with patch("services.briefing.deliver_briefing") as deliver:
        r = client.post("/jobs/briefing?kind=morning")
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    deliver.assert_not_called()


def test_briefing_job_bad_kind_is_400(client, monkeypatch):
    monkeypatch.setenv("EVI_BRIEFING_ENABLED", "true")
    with patch("services.briefing.deliver_briefing") as deliver:
        assert client.post("/jobs/briefing?kind=noon").status_code == 400
    deliver.assert_not_called()


def test_briefing_job_second_call_same_day_is_already_sent_and_sends_once(client, monkeypatch):
    monkeypatch.setenv("EVI_BRIEFING_ENABLED", "true")
    sent = []

    def fake_deliver(kind="morning", force=False, now=None):
        if sent and not force:
            return {"status": "already_sent", "kind": kind}
        sent.append(kind)
        return {"status": "sent", "kind": kind}

    with patch("services.briefing.deliver_briefing", side_effect=fake_deliver) as deliver:
        first = client.post("/jobs/briefing?kind=morning&wait=true").json()
        second = client.post("/jobs/briefing?kind=morning&wait=true").json()
        forced = client.post("/jobs/briefing?kind=morning&force=true&wait=true").json()
    assert first["status"] == "sent" and second["status"] == "already_sent"
    assert forced["status"] == "sent" and len(sent) == 2
    assert deliver.call_args_list[1].kwargs == {"kind": "morning", "force": False}
    assert deliver.call_args_list[2].kwargs == {"kind": "morning", "force": True}


def test_briefing_job_failure_is_http_200_status_failed(client, monkeypatch):
    monkeypatch.setenv("EVI_BRIEFING_ENABLED", "true")
    with patch("services.briefing.deliver_briefing", side_effect=RuntimeError("boom")):
        r = client.post("/jobs/briefing?kind=evening&wait=true")
    assert r.status_code == 200
    assert r.json()["status"] == "failed" and r.json()["kind"] == "evening"


# --- background execution of /jobs/probe and /jobs/briefing -------------------
# Windmill has ONE worker: these endpoints must return at once instead of holding it.


@pytest.fixture
def bg_clean():
    import threading
    import time

    yield
    deadline = time.time() + 5
    while time.time() < deadline and any(t.name.startswith("job-") for t in threading.enumerate()):
        time.sleep(0.01)


def test_probe_job_returns_immediately_and_runs_in_background(client, bg_clean):
    import threading

    started, release, done = threading.Event(), threading.Event(), threading.Event()

    def slow_probe():
        started.set()
        release.wait(5)
        done.set()
        return {"ok": True}

    with patch("services.probe.run_probe", side_effect=slow_probe):
        r = client.post("/jobs/probe")  # returns while the job is still blocked
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"
        assert started.wait(2) and not done.is_set()
        release.set()
        assert done.wait(2)


def test_probe_job_overlapping_call_is_already_running(client, bg_clean):
    import threading

    started, release = threading.Event(), threading.Event()

    def slow_probe():
        started.set()
        release.wait(5)
        return {"ok": True}

    with patch("services.probe.run_probe", side_effect=slow_probe) as probe:
        assert client.post("/jobs/probe").json()["status"] == "accepted"
        assert started.wait(2)
        assert client.post("/jobs/probe").json()["status"] == "already_running"
        assert client.post("/jobs/probe?wait=true").json()["status"] == "already_running"
        release.set()
    assert probe.call_count == 1


def test_probe_job_wait_true_runs_inline(client):
    with patch("services.probe.run_probe", return_value={"ok": True, "failed": []}) as probe:
        r = client.post("/jobs/probe?wait=true")
    assert r.json() == {"ok": True, "failed": []}
    probe.assert_called_once()


def test_probe_job_exception_in_background_is_soft_failed(client, bg_clean, caplog):
    import threading
    import time

    with caplog.at_level("WARNING", logger="evi.softfail"):
        with patch("services.probe.run_probe", side_effect=RuntimeError("boom")):
            assert client.post("/jobs/probe").json()["status"] == "accepted"
            deadline = time.time() + 3
            while time.time() < deadline and "boom" not in caplog.text:
                time.sleep(0.01)
    assert "background_jobs.probe" in caplog.text and "boom" in caplog.text
    # lock released: a new run is accepted again
    deadline = time.time() + 3
    while time.time() < deadline and any(t.name == "job-probe" for t in threading.enumerate()):
        time.sleep(0.01)
    with patch("services.probe.run_probe", return_value={"ok": True}):
        assert client.post("/jobs/probe").json()["status"] == "accepted"


def test_briefing_job_returns_immediately_and_runs_in_background(client, monkeypatch, bg_clean):
    import threading

    monkeypatch.setenv("EVI_BRIEFING_ENABLED", "true")
    started, release, done = threading.Event(), threading.Event(), threading.Event()

    def slow_deliver(kind="morning", force=False, now=None):
        started.set()
        release.wait(5)
        done.set()
        return {"status": "sent"}

    with patch("services.briefing.deliver_briefing", side_effect=slow_deliver):
        r = client.post("/jobs/briefing?kind=morning")
        assert r.status_code == 200 and r.json()["status"] == "accepted"
        assert started.wait(2) and not done.is_set()
        assert client.post("/jobs/briefing?kind=morning").json()["status"] == "already_running"
        release.set()
        assert done.wait(2)
