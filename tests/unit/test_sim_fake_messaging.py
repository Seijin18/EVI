"""Fake Telegram + fake Evolution + combined fakes app (evi-sim-harness 2.3)."""
from __future__ import annotations

import socket
import threading
import time

import pytest

pytest.importorskip("starlette")
from starlette.testclient import TestClient  # noqa: E402

from testing.sim.fakes import build_app  # noqa: E402

TOK = "/botsim-token"


@pytest.fixture
def client():
    with TestClient(build_app()) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_bad_token_401(client):
    r = client.get("/botwrong/getMe")
    assert r.status_code == 401 and r.json()["ok"] is False


def test_getme_and_delete_webhook(client):
    assert client.get(f"{TOK}/getMe").json()["result"]["is_bot"] is True
    assert client.get(f"{TOK}/deleteWebhook?drop_pending_updates=false").json() == {
        "ok": True,
        "result": True,
    }


def test_updates_shape_and_offset_ack(client):
    uid = client.post("/_sim/telegram/updates", json={"text": "Oi"}).json()["update_id"]
    uid2 = client.post("/_sim/telegram/updates", json={"text": "Dois", "chat_id": 42}).json()["update_id"]
    res = client.get(f"{TOK}/getUpdates?offset=0&timeout=0").json()["result"]
    assert [u["update_id"] for u in res] == [uid, uid2]
    m = res[0]["message"]
    assert m["text"] == "Oi" and m["chat"]["type"] == "private"
    assert m["from"]["id"] == m["chat"]["id"] and "date" in m and "message_id" in m
    assert res[1]["message"]["chat"]["id"] == 42
    # offset acks the first
    res = client.get(f"{TOK}/getUpdates?offset={uid + 1}&timeout=0").json()["result"]
    assert [u["update_id"] for u in res] == [uid2]
    assert client.get(f"{TOK}/getUpdates?offset={uid2 + 1}&timeout=0").json()["result"] == []


def test_default_chat_id_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    with TestClient(build_app()) as c:
        c.post("/_sim/telegram/updates", json={"text": "x"})
        res = c.get(f"{TOK}/getUpdates?timeout=0").json()["result"]
    assert res[0]["message"]["chat"]["id"] == 123456


def test_long_poll_blocks_until_enqueue(client):
    def later():
        time.sleep(0.4)
        client.post("/_sim/telegram/updates", json={"text": "tarde"})

    th = threading.Thread(target=later)
    th.start()
    t0 = time.monotonic()
    res = client.get(f"{TOK}/getUpdates?offset=0&timeout=5").json()["result"]
    th.join()
    assert res and res[0]["message"]["text"] == "tarde"
    assert 0.3 < time.monotonic() - t0 < 4


def test_long_poll_times_out_empty(client):
    t0 = time.monotonic()
    assert client.get(f"{TOK}/getUpdates?timeout=1").json()["result"] == []
    assert time.monotonic() - t0 >= 0.9


def test_send_message_captured(client):
    r = client.post(f"{TOK}/sendMessage", json={"chat_id": "900000001", "text": "olá"})
    assert r.status_code == 200 and r.json()["result"]["text"] == "olá"
    sent = client.get("/_sim/telegram/sent").json()
    assert len(sent) == 1 and sent[0]["chat_id"] == 900000001 and sent[0]["text"] == "olá"


def test_unknown_telegram_method_500(client):
    r = client.get(f"{TOK}/setMyCommands")
    assert r.status_code == 500 and "setMyCommands" in r.json()["description"]


def test_transient_fault_then_success(client):
    assert client.post("/_sim/telegram/faults", json={"sendMessage": "transient", "count": 2}).json()["ok"]
    for _ in range(2):
        assert client.post(f"{TOK}/sendMessage", json={"chat_id": 1, "text": "a"}).status_code == 500
    assert client.post(f"{TOK}/sendMessage", json={"chat_id": 1, "text": "a"}).status_code == 200
    assert len(client.get("/_sim/telegram/sent").json()) == 1


def test_bad_fault_400(client):
    assert client.post("/_sim/telegram/faults", json={"sendMessage": "nope"}).status_code == 400


@pytest.fixture
def live_server():
    """Real uvicorn on a free port so urllib-based production code hits the fake."""
    uvicorn = pytest.importorskip("uvicorn")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    th.join(timeout=5)


def test_real_sender_retries_transient_failure(live_server, monkeypatch):
    import json
    import urllib.request

    from services.telegram_notify import send_telegram_message

    monkeypatch.setenv("TELEGRAM_API_BASE", live_server)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "sim-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "900000001")
    monkeypatch.setenv("EVI_SEND_RETRY_BACKOFF_SEC", "0")

    def post(path, body):
        req = urllib.request.Request(
            live_server + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        return urllib.request.urlopen(req, timeout=5).read()

    post("/_sim/telegram/faults", {"sendMessage": "transient", "count": 1})
    res = send_telegram_message("resposta")
    assert res and res.attempts == 2
    sent = json.loads(urllib.request.urlopen(live_server + "/_sim/telegram/sent", timeout=5).read())
    assert [m["text"] for m in sent] == ["resposta"]


def test_real_poller_fetch_updates(live_server, monkeypatch):
    from services import telegram_poller

    monkeypatch.setenv("TELEGRAM_API_BASE", live_server)
    import json
    import urllib.request

    req = urllib.request.Request(
        live_server + "/_sim/telegram/updates",
        data=json.dumps({"text": "Oi"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    uid = json.loads(urllib.request.urlopen(req, timeout=5).read())["update_id"]
    assert telegram_poller.delete_webhook("sim-token") is True
    ups = telegram_poller.fetch_updates("sim-token", offset=0, timeout=2)
    assert [u["update_id"] for u in ups] == [uid]
    assert telegram_poller.fetch_updates("sim-token", offset=uid + 1, timeout=0) == []


def test_long_poll_does_not_stall_concurrent_requests(live_server):
    """A held getUpdates must not block sendMessage / control calls, and must return as
    soon as an update is enqueued (not when its 30 s deadline expires)."""
    import json
    import urllib.request

    base = live_server

    def call(path, body=None, timeout=10):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            base + path, data=data, headers={"content-type": "application/json"} if data else {}
        )
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

    got: dict = {}

    def poll():
        t0 = time.monotonic()
        got["res"] = call("/botsim-token/getUpdates?offset=0&timeout=30", timeout=40)
        got["dt"] = time.monotonic() - t0

    th = threading.Thread(target=poll)
    th.start()
    time.sleep(0.3)  # the long poll is now parked server-side
    t0 = time.monotonic()
    sent = call("/botsim-token/sendMessage", {"chat_id": 1, "text": "oi"})
    call("/_sim/state")
    assert sent["ok"] is True
    assert time.monotonic() - t0 < 2, "sendMessage/_sim stalled behind a held getUpdates"
    call("/_sim/telegram/updates", {"text": "chegou"})
    th.join(timeout=10)
    assert not th.is_alive()
    assert got["dt"] < 3, "long poll did not wake on enqueue"
    assert got["res"]["result"][0]["message"]["text"] == "chegou"


def test_sim_image_does_not_fake_the_monotonic_clock():
    """libfaketime shifts CLOCK_MONOTONIC when /sim/clock is rewritten unless told not to;
    a backward jump froze the fakes' asyncio timers (long polls ~60 s late)."""
    from pathlib import Path

    df = (Path(__file__).resolve().parents[2] / "agent" / "Dockerfile.sim").read_text()
    assert "FAKETIME_DONT_FAKE_MONOTONIC=1" in df


# ------------------------------------------------------------------ evolution
EVO = {"apikey": "k"}


@pytest.fixture
def evo(monkeypatch):
    monkeypatch.setenv("EVOLUTION_API_KEY", "k")
    with TestClient(build_app()) as c:
        yield c


def test_evolution_send_text_captured_with_recipient(evo):
    r = evo.post("/message/sendText/sim", json={"number": "5511999990000", "text": "[EVI] oi"}, headers=EVO)
    assert r.status_code == 201
    sent = evo.get("/_sim/evolution/sent").json()
    assert sent[0]["number"] == "5511999990000" and sent[0]["text"] == "[EVI] oi"
    assert sent[0]["jid"] == "5511999990000@s.whatsapp.net"


def test_evolution_apikey_checked(evo):
    r = evo.post("/message/sendText/sim", json={"number": "1", "text": "x"}, headers={"apikey": "bad"})
    assert r.status_code == 401
    assert evo.get("/_sim/evolution/sent").json() == []


def test_evolution_seeded_reads(evo):
    evo.post(
        "/_sim/evolution/seed",
        json={
            "contacts": [{"remoteJid": "551188@s.whatsapp.net", "pushName": "Maria"}],
            "chats": [{"remoteJid": "551188@s.whatsapp.net"}],
            "messages": {"551188@s.whatsapp.net": [{"key": {"remoteJid": "551188@s.whatsapp.net"}}]},
            "profiles": {"551188": {"name": "Maria"}},
        },
    )
    assert evo.post("/chat/findContacts/sim", json={"page": 1}, headers=EVO).json()[0]["pushName"] == "Maria"
    assert len(evo.post("/chat/findChats/sim", json={}, headers=EVO).json()) == 1
    body = {"where": {"key": {"remoteJid": "551188@s.whatsapp.net"}}}
    assert evo.post("/chat/findMessages/sim", json=body, headers=EVO).json()["messages"]["total"] == 1
    assert evo.post("/chat/fetchProfile/sim", json={"number": "551188"}, headers=EVO).json()["name"] == "Maria"


def test_real_evolution_client_against_fake(live_server, monkeypatch):
    from messaging.evolution import EvolutionClient

    monkeypatch.setenv("EVOLUTION_SERVER_URL", live_server)
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "sim")
    monkeypatch.setenv("EVOLUTION_API_KEY", "")
    assert EvolutionClient().send_text("5511900000000@s.whatsapp.net", "oi")
    import json
    import urllib.request

    sent = json.loads(urllib.request.urlopen(live_server + "/_sim/evolution/sent", timeout=5).read())
    assert sent[0]["number"] == "5511900000000" and sent[0]["text"].endswith("oi")


def test_unknown_endpoint_500_names_url(client):
    r = client.post("/instance/connect/sim", json={})
    assert r.status_code == 500 and "/instance/connect/sim" in r.json()["error"]


# ------------------------------------------------------------------ combined
def test_combined_state_seed_and_reset(client):
    client.post("/_sim/seed", json={"google": {"tasks": [{"title": "t"}]}, "evolution": {"contacts": [{"a": 1}]}})
    client.post(f"{TOK}/sendMessage", json={"chat_id": 1, "text": "a"})
    client.post("/message/sendText/sim", json={"number": "1", "text": "b"})
    client.post("/_sim/faults", json={"*": "http_500"})
    st = client.get("/_sim/state").json()
    assert set(st) == {"google", "windmill_calls", "telegram_sent", "evolution_sent", "media_requests"}
    assert st["google"]["tasks"] and len(st["telegram_sent"]) == 1 and len(st["evolution_sent"]) == 1
    client.post("/_sim/telegram/updates", json={"text": "pend"})
    client.post("/_sim/telegram/faults", json={"sendMessage": "transient"})
    assert client.post("/_sim/reset").json()["ok"]
    st = client.get("/_sim/state").json()
    assert st["google"]["tasks"] == [] and st["telegram_sent"] == [] and st["evolution_sent"] == []
    assert client.get(f"{TOK}/getUpdates?timeout=0").json()["result"] == []
    assert client.post(f"{TOK}/sendMessage", json={"chat_id": 1, "text": "ok"}).status_code == 200
    assert client.get("/_sim/calls").json() == []


def test_windmill_shares_google_instance():
    app = build_app()
    assert app.state.windmill.google is app.state.google


def test_seed_plain_google_still_works(client):
    client.post("/_sim/seed", json={"tasks": [{"title": "x"}]})
    assert client.get("/_sim/state").json()["google"]["tasks"]


# ------------------------------------------------------------------ voice (evi-voice-input)
def test_telegram_voice_getfile_and_download(client):
    import base64

    audio = b"OggS-fake-opus-bytes"
    r = client.post("/_sim/telegram/voice", json={"audio_b64": base64.b64encode(audio).decode(), "duration_s": 7})
    assert r.status_code == 200
    upd = client.get(f"{TOK}/getUpdates?offset=0&timeout=0").json()["result"][0]
    assert upd["update_id"] == r.json()["update_id"]
    msg = upd["message"]
    voice = msg["voice"]
    assert "text" not in msg and msg["chat"]["type"] == "private"
    assert voice["duration"] == 7 and voice["file_size"] == len(audio) and voice["mime_type"] == "audio/ogg"
    got = client.get(f"{TOK}/getFile", params={"file_id": voice["file_id"]}).json()
    assert got["ok"] and got["result"]["file_size"] == len(audio)
    dl = client.get(f"/file/botsim-token/{got['result']['file_path']}")
    assert dl.status_code == 200 and dl.content == audio


def test_telegram_getfile_unknown_and_bad_token(client):
    assert client.get(f"{TOK}/getFile", params={"file_id": "nope"}).status_code == 400
    assert client.get("/file/botsim-token/voice/missing.oga").status_code == 404
    assert client.get("/file/botwrong/voice/x.oga").status_code == 401


def test_telegram_voice_requires_audio(client):
    assert client.post("/_sim/telegram/voice", json={}).status_code == 400


def test_evolution_media_served_by_message_id_and_logged(client):
    import base64

    audio = b"OggS-wa-audio"
    assert client.post("/_sim/evolution/media", json={"id": "M1", "audio_b64": base64.b64encode(audio).decode()}).status_code == 200
    key = {"id": "M1", "remoteJid": "5500000000001@s.whatsapp.net"}
    r = client.post("/chat/getBase64FromMediaMessage/sim", json={"message": {"key": key}, "convertToMp4": False})
    assert r.status_code == 201
    assert base64.b64decode(r.json()["base64"]) == audio and r.json()["mimetype"].startswith("audio/ogg")
    miss = client.post("/chat/getBase64FromMediaMessage/sim", json={"message": {"key": {"id": "X"}}})
    assert miss.status_code == 404
    reqs = client.get("/_sim/state").json()["media_requests"]
    assert [m["id"] for m in reqs] == ["M1", "X"]
    client.post("/_sim/reset")
    assert client.get("/_sim/state").json()["media_requests"] == []
    assert client.post("/chat/getBase64FromMediaMessage/sim", json={"message": {"key": key}}).status_code == 404


def test_evolution_recorded_message_served_by_find_messages(evo):
    jid = "5511900000001@s.whatsapp.net"
    rec = {"key": {"id": "A1", "remoteJid": jid, "fromMe": True}, "messageTimestamp": 1760000000, "message": {"conversation": "Pode deixar"}}
    assert evo.post("/_sim/evolution/message", json=rec).json() == {"ok": True}
    body = {"where": {"key": {"remoteJid": jid}}}
    got = evo.post("/chat/findMessages/sim", json=body, headers=EVO).json()["messages"]["records"]
    assert got == [rec]
    other = evo.post("/chat/findMessages/sim", json={"where": {"key": {"remoteJid": "x@s.whatsapp.net"}}}, headers=EVO).json()
    assert other["messages"]["records"] == []
    evo.post("/_sim/reset")
    assert evo.post("/chat/findMessages/sim", json=body, headers=EVO).json()["messages"]["records"] == []


def test_evolution_connection_state_default_seed_and_change(evo):
    r = evo.get("/instance/connectionState/sim", headers=EVO)
    assert r.status_code == 200 and r.json()["instance"]["state"] == "open"
    evo.post("/_sim/evolution/seed", json={"state": "close"})
    assert evo.get("/instance/connectionState/sim", headers=EVO).json() == {
        "instance": {"instanceName": "sim", "state": "close"}
    }
    evo.post("/_sim/evolution/state", json={"state": "open"})
    assert evo.get("/instance/connectionState/sim", headers=EVO).json()["instance"]["state"] == "open"
    assert evo.get("/instance/connectionState/sim", headers={"apikey": "bad"}).status_code == 401
