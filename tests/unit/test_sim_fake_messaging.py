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
    assert set(st) == {"google", "windmill_calls", "telegram_sent", "evolution_sent"}
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
