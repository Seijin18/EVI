"""SCN-REL-01: watchdog alerts once after the 2nd failure, once on recovery.
SCN-REL-03: WhatsApp (Evolution connectionState) alerts once, reconnection once."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evi-watchdog"
TOKEN = "SECRET-TOKEN-123"
WA_KEY = "SECRET-EVO-KEY-456"


class Fake:
    def __init__(self):
        self.mode = "ok"
        self.sent = []
        self.wa_state = "open"
        self.wa_requests = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/instance/connectionState/"):
                    fake.wa_requests.append((self.path, self.headers.get("apikey")))
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({"instance": {"instanceName": "evi", "state": fake.wa_state}}).encode())
                    return
                if fake.mode == "hang":
                    time.sleep(3)
                    return
                if fake.mode == "500":
                    self.send_response(500)
                    self.end_headers()
                    return
                body = json.dumps({"status": fake.mode}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                fake.sent.append((self.path, self.rfile.read(n).decode()))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


@pytest.fixture
def env(tmp_path):
    f = Fake()
    e = {
        **os.environ,
        "EVI_WATCHDOG_URL": f.url + "/health",
        "EVI_WATCHDOG_TIMEOUT": "1",
        "TELEGRAM_API_BASE": f.url,
        "TELEGRAM_BOT_TOKEN": TOKEN,
        "TELEGRAM_CHAT_ID": "1",
        "XDG_STATE_HOME": str(tmp_path),
        # isolate from the real repo .env; WhatsApp check off unless a test enables it
        "EVI_WATCHDOG_ENV_FILE": str(tmp_path / "no.env"),
        "EVI_SOURCE_ALERTS_ENABLED": "false",
    }
    for k in ("EVOLUTION_API_KEY", "EVOLUTION_INSTANCE_NAME"):
        e.pop(k, None)
    yield f, e
    f.srv.shutdown()


def run(e, *args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], env=e, capture_output=True, text=True, timeout=30, check=False)
    assert TOKEN not in p.stdout + p.stderr and WA_KEY not in p.stdout + p.stderr
    return p


def test_fail_fail_fail_ok_alerts_once_then_recovers(env):
    f, e = env
    f.mode = "500"
    run(e)
    assert f.sent == []
    run(e)
    assert len(f.sent) == 1 and f"/bot{TOKEN}/sendMessage" == f.sent[0][0]
    assert "fora+do+ar" in f.sent[0][1] and "HTTP+500" in f.sent[0][1]
    run(e)
    assert len(f.sent) == 1
    f.mode = "ok"
    run(e)
    assert len(f.sent) == 2 and "voltou" in f.sent[1][1]
    run(e)
    assert len(f.sent) == 2


@pytest.mark.parametrize("mode", ["down", "hang"])
def test_down_and_timeout_count_as_failure(env, mode):
    f, e = env
    f.mode = mode
    run(e)
    run(e)
    assert len(f.sent) == 1


def test_degraded_never_alerts(env):
    f, e = env
    f.mode = "degraded"
    for _ in range(4):
        assert "ok" in run(e).stdout
    assert f.sent == []


def test_dry_run_sends_nothing_and_keeps_state(env, tmp_path):
    f, e = env
    f.mode = "down"
    for _ in range(3):
        out = run(e, "--dry-run").stdout
        assert "fail 1" in out
    assert f.sent == [] and not (tmp_path / "evi-watchdog").exists()
    run(e)
    out = run(e, "--dry-run").stdout
    assert "would alert" in out and f.sent == []


def test_dry_run_reports_recovery(env):
    f, e = env
    f.mode = "down"
    run(e)
    run(e)
    f.mode = "ok"
    assert "would send recovery" in run(e, "--dry-run").stdout
    assert len(f.sent) == 1


def test_unreachable_server_counts_as_failure(env):
    f, e = env
    e["EVI_WATCHDOG_URL"] = "http://127.0.0.1:1/health"
    run(e)
    assert run(e).returncode == 0
    assert len(f.sent) == 1 and "sem+conex" in f.sent[0][1]


@pytest.fixture
def wa_env(env):
    f, e = env
    e["EVI_SOURCE_ALERTS_ENABLED"] = "true"
    e["EVOLUTION_API_KEY"] = WA_KEY
    e["EVI_WATCHDOG_EVOLUTION_URL"] = f.url
    return f, e


def test_whatsapp_close_close_close_open_alerts_once_then_reconnects(wa_env):
    f, e = wa_env
    f.wa_state = "close"
    run(e)
    assert f.sent == []
    run(e)
    assert len(f.sent) == 1 and "WhatsApp+desconectado" in f.sent[0][1] and "instância+evi" in f.sent[0][1].replace("%C3%A2ncia", "ância")
    run(e)
    assert len(f.sent) == 1
    f.wa_state = "open"
    run(e)
    assert len(f.sent) == 2 and "WhatsApp+reconectado" in f.sent[1][1]
    run(e)
    assert len(f.sent) == 2
    assert not any("EVI" in m[1] and "fora" in m[1] for m in f.sent)  # agent healthy: no agent alert
    assert f.wa_requests[0] == ("/instance/connectionState/evi", WA_KEY)


def test_whatsapp_unreachable_counts_as_failure(wa_env):
    f, e = wa_env
    e["EVI_WATCHDOG_EVOLUTION_URL"] = "http://127.0.0.1:1"
    run(e)
    run(e)
    assert len(f.sent) == 1 and "WhatsApp+desconectado" in f.sent[0][1]


def test_whatsapp_and_agent_alerts_are_independent(wa_env):
    f, e = wa_env
    f.mode = "500"
    f.wa_state = "close"
    run(e)
    run(e)
    assert len(f.sent) == 2


def test_whatsapp_missing_key_skips_check(wa_env):
    f, e = wa_env
    del e["EVOLUTION_API_KEY"]
    f.wa_state = "close"
    for _ in range(3):
        run(e)
    assert f.sent == [] and f.wa_requests == []


def test_whatsapp_flag_false_skips_check(wa_env):
    f, e = wa_env
    e["EVI_SOURCE_ALERTS_ENABLED"] = "false"
    f.wa_state = "close"
    for _ in range(3):
        run(e)
    assert f.sent == [] and f.wa_requests == []


def test_whatsapp_dry_run_sends_nothing_and_writes_nothing(wa_env, tmp_path):
    f, e = wa_env
    f.wa_state = "close"
    for _ in range(3):
        run(e, "--dry-run")
    assert f.sent == [] and not (tmp_path / "evi-watchdog").exists()


def test_old_state_file_without_wa_keys_still_loads(wa_env, tmp_path):
    f, e = wa_env
    d = tmp_path / "evi-watchdog"
    d.mkdir()
    (d / "state").write_text("failures=0\nalerted=0\nsince=0\n")
    f.wa_state = "close"
    run(e)
    run(e)
    assert len(f.sent) == 1


def test_env_reader_only_reads_allowed_keys(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    envf.write_text("EVOLUTION_API_KEY='abc'\nOPENROUTER_API_KEY=nope\nEVOLUTION_INSTANCE_NAME=inst\n")
    monkeypatch.setenv("EVI_WATCHDOG_ENV_FILE", str(envf))
    for k in ("EVOLUTION_API_KEY", "OPENROUTER_API_KEY", "EVOLUTION_INSTANCE_NAME"):
        monkeypatch.delenv(k, raising=False)
    loader = importlib.machinery.SourceFileLoader("evi_watchdog", str(SCRIPT))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("evi_watchdog", loader))
    loader.exec_module(mod)
    assert mod.env_value("EVOLUTION_API_KEY") == "abc"
    assert mod.env_value("EVOLUTION_INSTANCE_NAME") == "inst"
    assert mod.env_value("OPENROUTER_API_KEY") == ""
