"""SCN-REL-01: watchdog alerts once after the 2nd failure, once on recovery."""
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


class Fake:
    def __init__(self):
        self.mode = "ok"
        self.sent = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
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
    }
    yield f, e
    f.srv.shutdown()


def run(e, *args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], env=e, capture_output=True, text=True, timeout=30, check=False)
    assert TOKEN not in p.stdout + p.stderr
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
