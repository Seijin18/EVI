"""SCN-BRIEF-06: Windmill briefing script POSTs /jobs/briefing with the heartbeat envelope."""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SCRIPT = Path(__file__).resolve().parents[2] / "windmill/f/integrations/briefing.py"


def _load():
    spec = importlib.util.spec_from_file_location("wm_briefing", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _serve(status, payload):
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            u = urlparse(self.path)
            seen["path"] = u.path
            seen["query"] = parse_qs(u.query)
            seen["key"] = self.headers.get("X-Api-Key")
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def test_ok_envelope_and_request(monkeypatch):
    srv, seen = _serve(200, {"sent": True})
    try:
        monkeypatch.setenv("EVI_API_URL", f"http://127.0.0.1:{srv.server_port}/")
        monkeypatch.setenv("EVI_API_KEY", "k123")
        out = _load().main(kind="evening", force=True)
    finally:
        srv.shutdown()
    assert out == {"status": "ok", "sent": True}
    assert seen["path"] == "/jobs/briefing"
    assert seen["query"] == {"kind": ["evening"], "force": ["true"]}
    assert seen["key"] == "k123"


def test_defaults_morning_no_force(monkeypatch):
    srv, seen = _serve(200, {})
    try:
        monkeypatch.setenv("EVI_API_URL", f"http://127.0.0.1:{srv.server_port}")
        monkeypatch.setenv("EVI_API_KEY", "k")
        _load().main()
    finally:
        srv.shutdown()
    assert seen["query"] == {"kind": ["morning"], "force": ["false"]}


def test_http_error_envelope(monkeypatch):
    srv, _ = _serve(500, {"detail": "boom"})
    try:
        monkeypatch.setenv("EVI_API_URL", f"http://127.0.0.1:{srv.server_port}")
        out = _load().main()
    finally:
        srv.shutdown()
    assert out["status"] == "error"
    assert out["http"] == 500
    assert "boom" in out["detail"]


def test_connection_error_envelope(monkeypatch):
    monkeypatch.setenv("EVI_API_URL", "http://127.0.0.1:1")
    out = _load().main()
    assert out["status"] == "error"
    assert "detail" in out
