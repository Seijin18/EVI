"""Unit tests for the stateful fake Google (agent/testing/sim/fake_google.py)."""

import importlib.util
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pytest

from testing.sim.fake_google import FakeGoogle, build_app

ROOT = Path(__file__).resolve().parents[2]
AUTH = {"Authorization": "Bearer tok"}
TZ = ZoneInfo("America/Sao_Paulo")


class _Resp:
    def __init__(self, status, body):
        self.status, self._b = status, body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen_for(fake):
    import urllib.error

    def urlopen(req, timeout=None):
        status, body, _ = fake.handle(
            req.get_method(), req.full_url, dict(req.header_items()), req.data
        )
        if status >= 400:
            raise urllib.error.HTTPError(req.full_url, status, "err", {}, __import__("io").BytesIO(body))
        return _Resp(status, body)

    return urlopen


def _script(name):
    spec = importlib.util.spec_from_file_location(f"wm_{name}", ROOT / "windmill/f/integrations" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call(g, method, url, body=None):
    s, b, h = g.handle(method, url, AUTH, json.dumps(body).encode() if body is not None else None)
    return s, b


def test_unimplemented_endpoint_is_500_with_url():
    g = FakeGoogle()
    status, body = _call(g, "GET", "https://www.googleapis.com/drive/v3/files?q=x")
    assert status == 500
    assert b"https://www.googleapis.com/drive/v3/files?q=x" in body
    status, body = _call(g, "DELETE", "https://gmail.googleapis.com/gmail/v1/users/me/messages/batchDelete")
    assert status == 500 and b"batchDelete" in body


def test_unsupported_gmail_query_operator_is_500():
    g = FakeGoogle()
    g.seed({"gmail": [{"from": "a", "subject": "s", "snippet": "x"}]})
    status, body = _call(g, "GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=has%3Aattachment")
    assert status == 500


def test_requires_bearer():
    s, _, _ = FakeGoogle().handle("GET", "https://www.googleapis.com/calendar/v3/users/me/calendarList", {}, None)
    assert s == 401


def test_schedule_event_script_creates_event_in_timezone(monkeypatch):
    """SCN-SIM-03: real schedule_event script -> event in fake calendar."""
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    g = FakeGoogle()
    mod = _script("schedule_event")
    with mock.patch.object(urllib.request, "urlopen", _urlopen_for(g)):
        out = mod.main(
            title="Dentista",
            start_time="2026-10-12T15:00:00",
            end_time="2026-10-12T16:00:00",
            description="rotina",
            gcal={"token": "tok"},
        )
    assert out["status"] == "created"
    st = g.state()
    assert len(st["calendar"]) == 1 and len(st["created"]["calendar"]) == 1
    ev = st["calendar"][0]
    assert ev["summary"] == "Dentista" and ev["description"] == "rotina"
    assert ev["start"] == "2026-10-12T15:00:00-03:00"
    assert datetime.fromisoformat(ev["start"]).utcoffset() == timedelta(hours=-3)
    assert out["event_id"] == ev["id"]


def test_list_events_script_filters_window_and_orders():
    g = FakeGoogle()
    now = datetime.now(TZ)
    day = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    g.seed(
        {
            "calendar": [
                {"summary": "B", "start": (day + timedelta(hours=3)).isoformat(), "end": (day + timedelta(hours=4)).isoformat()},
                {"summary": "A", "start": day.isoformat(), "end": (day + timedelta(hours=1)).isoformat()},
                {"summary": "Far", "start": (now + timedelta(days=30)).isoformat(), "end": (now + timedelta(days=30, hours=1)).isoformat()},
            ]
        }
    )
    mod = _script("list_events")
    with mock.patch.object(urllib.request, "urlopen", _urlopen_for(g)):
        out = mod.main(gcal={"token": "tok"}, days_ahead=3)
        named = mod.main(gcal={"token": "tok"}, calendar_id="EVI", days_ahead=3)
    assert [e["summary"] for e in out["events"]] == ["A", "B"]
    assert named["count"] == 2


def test_tasks_scripts_roundtrip():
    g = FakeGoogle()
    g.seed({"tasks": [{"title": "Pagar luz", "due": "2026-10-15"}, {"title": "Velha", "status": "completed"}]})
    ct, lt = _script("create_task"), _script("list_tasks")
    with mock.patch.object(urllib.request, "urlopen", _urlopen_for(g)):
        created = ct.main(title="Comprar pão", due_date="2026-10-11", gtasks={"token": "tok"})
        listed = lt.main(gtasks={"token": "tok"})
        listed_all = lt.main(gtasks={"token": "tok"}, show_completed=True)
    assert created["status"] == "created" and created["task_id"]
    assert [t["title"] for t in listed["tasks"]] == ["Pagar luz", "Comprar pão"]
    assert listed["tasks"][1]["due"] == "2026-10-11"
    assert listed_all["count"] == 3
    assert [t["title"] for t in g.state()["created"]["tasks"]] == ["Comprar pão"]


def _mail_seed():
    now = datetime.now(TZ)
    return {
        "gmail": [
            {"id": "m1", "from": "Loja <promo@loja.com>", "subject": "50% off", "snippet": "oferta", "labels": ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"], "date": now.isoformat()},
            {"id": "m2", "from": "Ana <ana@x.com>", "subject": "Reunião", "snippet": "amanhã", "labels": ["INBOX"], "date": (now - timedelta(days=10)).isoformat()},
            {"id": "m3", "from": "Spam <promo@loja.com>", "subject": "Cupom", "snippet": "cupom", "labels": ["INBOX", "CATEGORY_PROMOTIONS"], "date": (now - timedelta(days=1)).isoformat()},
        ]
    }


def test_summarize_inbox_and_delete_scripts():
    g = FakeGoogle()
    g.seed(_mail_seed())
    with mock.patch.object(urllib.request, "urlopen", _urlopen_for(g)):
        inbox = _script("summarize_inbox").main(gmail={"token": "tok"})
        assert inbox["count"] == 3
        assert {"id": "m2", "subject": "Reunião", "from": "Ana <ana@x.com>"} in inbox["messages"]
        out = _script("delete_emails_by_query").main(q="category:promotions", gmail={"token": "tok"})
        assert sorted(out["deleted_ids"]) == ["m1", "m3"]
        out2 = _script("delete_emails").main(message_ids=["m2", "nope"], gmail={"token": "tok"})
        assert out2["deleted"] == 1 and out2["warnings"]
    st = g.state()
    assert st["trashed"] == ["m1", "m3", "m2"] and st["deleted"] == st["trashed"]
    assert st["gmail"] == []
    with mock.patch.object(urllib.request, "urlopen", _urlopen_for(g)):
        assert _script("summarize_inbox").main(gmail={"token": "tok"})["count"] == 0


@pytest.mark.parametrize(
    "q,ids",
    [
        ("is:unread", {"m1"}),
        ("category:promotions newer_than:2d", {"m1", "m3"}),
        ("category:promotions -is:unread", {"m3"}),
        ("from:ana", {"m2"}),
        ("subject:cupom", {"m3"}),
        ("older_than:5d", {"m2"}),
        ("reunião", {"m2"}),
        ('"50% off"', {"m1"}),
    ],
)
def test_gmail_query_subset(q, ids):
    g = FakeGoogle()
    g.seed(_mail_seed())
    s, b = _call(g, "GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={quote(q)}")
    assert s == 200
    assert {m["id"] for m in json.loads(b).get("messages", [])} == ids


def test_reset_and_http_app():
    from starlette.testclient import TestClient

    g = FakeGoogle()
    c = TestClient(build_app(g))
    assert c.post("/_sim/seed", json={"tasks": [{"title": "x"}]}).status_code == 200
    assert c.get("/_sim/state").json()["tasks"][0]["title"] == "x"
    r = c.get("/tasks/v1/lists/@default/tasks", headers=AUTH)
    assert r.json()["items"][0]["title"] == "x"
    r = c.get("/nope/unknown", headers=AUTH)
    assert r.status_code == 500 and "/nope/unknown" in r.text
    c.post("/_sim/reset")
    assert c.get("/_sim/state").json()["tasks"] == []
