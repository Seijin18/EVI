"""Unit tests for the fake Windmill (agent/testing/sim/fake_windmill.py).

Runs the REAL scripts in windmill/f/integrations/ against FakeGoogle and checks
envelopes with the agent's own ``parse_windmill_result``.
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from services.tool_result import (
    HTTP_ERROR,
    OAUTH,
    UNPARSEABLE,
    UPSTREAM_ERROR,
    parse_windmill_result,
)
from testing.sim.fake_google import FakeGoogle
from testing.sim.fake_windmill import FakeWindmill, build_app

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "windmill" / "f" / "integrations"
RUN = "/api/w/evi/jobs/run_wait_result/p/f/integrations/"
ASYNC = "/api/w/evi/jobs/run/p/f/integrations/"

SEED = {
    "calendar": [
        {"summary": "Reuniao", "start": "2099-01-01T10:00:00", "end": "2099-01-01T11:00:00"}
    ],
    "tasks": [{"title": "Comprar pao"}],
    "gmail": [
        {"id": "m1", "from": "a@x.com", "subject": "Oi", "snippet": "ola", "labels": ["INBOX", "UNREAD"]},
        {"id": "m2", "from": "b@x.com", "subject": "Promo", "snippet": "off", "labels": ["INBOX", "CATEGORY_PROMOTIONS"]},
    ],
}

# the 8 operations the agent calls (agent/integrations/windmill.py _OPERATION_MAP)
OPS = {
    "schedule_event": {
        "title": "Dentista",
        "start_time": "2099-02-01T09:00:00",
        "end_time": "2099-02-01T10:00:00",
        "gcal": "$res:gcal",
    },
    "list_events": {"gcal": "$res:gcal", "days_ahead": 3650},
    "create_task": {"title": "Pagar conta", "due_date": "2099-03-01", "gtasks": "$res:gtasks"},
    "list_tasks": {"gtasks": "$res:gtasks"},
    "summarize_inbox": {"gmail": "$res:gmail"},
    "delete_emails": {"message_ids": ["m1"], "gmail": "$res:gmail"},
    "delete_emails_by_query": {"q": "category:promotions", "gmail": "$res:gmail"},
    "list_calendars": {"gcal": "$res:gcal"},
}
RESOURCE_ENV = {
    "schedule_event": "WINDMILL_GCAL_RESOURCE",
    "list_events": "WINDMILL_GCAL_RESOURCE",
    "list_calendars": "WINDMILL_GCAL_RESOURCE",
    "create_task": "WINDMILL_GTASKS_RESOURCE",
    "list_tasks": "WINDMILL_GTASKS_RESOURCE",
    "summarize_inbox": "WINDMILL_GMAIL_RESOURCE",
    "delete_emails": "WINDMILL_GMAIL_RESOURCE",
    "delete_emails_by_query": "WINDMILL_GMAIL_RESOURCE",
}


@pytest.fixture
def google():
    g = FakeGoogle()
    g.seed(SEED)
    return g


@pytest.fixture
def wm(google):
    return FakeWindmill(google, scripts_dir=str(SCRIPTS), timeout_sleep_sec=0.01)


def _client_post(wm, op, payload):
    """Call the agent's real _windmill_post with requests.post routed to the fake."""
    import requests
    from integrations.windmill import _windmill_post

    def fake_post(url, json=None, headers=None, timeout=None):
        import json as _json

        path = url.split("windmill-server:8000", 1)[1]
        status, body, hdrs = wm.handle("POST", path, headers or {}, _json.dumps(json).encode())
        r = requests.Response()
        r.status_code, r._content, r.url = status, body, url
        return r

    with mock.patch("integrations.windmill.requests.post", fake_post), mock.patch.dict(
        "os.environ", {"EVI_WINDMILL_RETRY_ATTEMPTS": "1"}
    ):
        default = f"http://windmill-server:8000{ASYNC}{op}"
        return _windmill_post("WINDMILL_SIM_UNSET", payload, default, wait_result=True)


def run(wm, op, payload):
    status, body, _ = wm.handle("POST", RUN + op, {}, json.dumps(payload).encode())
    return status, body.decode()


def test_eight_agent_ops_have_scripts():
    assert len(OPS) == 8
    for op in OPS:
        assert (SCRIPTS / f"{op}.py").is_file()


@pytest.mark.parametrize("op", sorted(OPS))
def test_real_script_succeeds_and_parses_ok(wm, op):
    status, raw = run(wm, op, OPS[op])
    assert status == 200, raw
    out = parse_windmill_result(raw, action=op, resource_env=RESOURCE_ENV[op])
    assert out.ok, (out.reason, raw)
    assert wm.calls[-1]["op"] == op and wm.calls[-1]["result"]["status"] in ("ok", "created")


def test_state_changes_reach_fake_google(wm, google):
    run(wm, "create_task", OPS["create_task"])
    run(wm, "schedule_event", OPS["schedule_event"])
    run(wm, "delete_emails", OPS["delete_emails"])
    st = google.state()
    assert [t["title"] for t in st["created"]["tasks"]] == ["Pagar conta"]
    assert [e["summary"] for e in st["created"]["calendar"]] == ["Dentista"]
    assert st["trashed"] == ["m1"]


def test_plain_resource_name_uses_fake_resources_endpoint(wm):
    # no "$res:" -> script itself fetches /api/w/<ws>/resources/get... via urlopen
    status, raw = run(wm, "list_tasks", {"gtasks": "u/evi/gtasks"})
    assert status == 200
    assert json.loads(raw)["status"] == "ok"
    s, b, _ = wm.handle("GET", "/api/w/evi/resources/get/u/evi/gtasks")
    assert s == 200 and json.loads(b)["value"]["token"]


@pytest.mark.parametrize("op", sorted(OPS))
def test_oauth_expired_is_classified_oauth(wm, op):
    wm.set_faults({op: "oauth_expired"})
    status, raw = run(wm, op, OPS[op])
    out = parse_windmill_result(raw, action=op, resource_env=RESOURCE_ENV[op])
    assert not out.ok, (status, raw)
    if op == "delete_emails":
        # Real script swallows the Google body ("m1: HTTP 401"), so the envelope
        # carries no OAuth marker and classifies as a generic upstream error.
        assert out.reason == UPSTREAM_ERROR and "HTTP 401" in raw
    else:
        assert out.reason == OAUTH, (status, raw)
    assert wm.calls[-1]["fault"] == "oauth_expired"


def test_fault_wildcard_and_clear(wm):
    wm.set_faults({"*": "http_500"})
    assert run(wm, "list_tasks", OPS["list_tasks"])[0] == 500
    wm.clear_faults()
    assert run(wm, "list_tasks", OPS["list_tasks"])[0] == 200


def test_http_500_matches_client_classification(wm):
    wm.set_faults({"create_task": "http_500"})
    status, raw = run(wm, "create_task", OPS["create_task"])
    assert status == 500
    assert json.loads(raw)["error"]["name"] == "InternalErr"
    # drive the agent's real client against the fake: non-2xx -> "Windmill request failed: ..."
    client_text = _client_post(wm, "create_task", OPS["create_task"])
    assert client_text.startswith("Windmill request failed")
    out = parse_windmill_result(client_text, action="criar tarefa")
    assert not out.ok and out.reason in (HTTP_ERROR, UNPARSEABLE)


def test_malformed_body_is_unparseable(wm):
    wm.set_faults({"list_events": "malformed_body"})
    status, raw = run(wm, "list_events", OPS["list_events"])
    assert status == 200
    with pytest.raises(ValueError):
        json.loads(raw)
    out = parse_windmill_result(raw, action="listar eventos", resource_env="WINDMILL_GCAL_RESOURCE")
    assert not out.ok and out.reason == UNPARSEABLE


def test_timeout_sleeps_configured_time_then_504():
    slept = []
    g = FakeGoogle()
    w = FakeWindmill(g, scripts_dir=str(SCRIPTS), timeout_sleep_sec=7.5, sleep=slept.append)
    w.set_faults({"summarize_inbox": "timeout"})
    status, _ = run(w, "summarize_inbox", OPS["summarize_inbox"])
    assert slept == [7.5] and status == 504
    assert w.calls[-1]["fault"] == "timeout"


def test_slow_fault_sleeps_then_executes_normally():
    slept = []
    w = FakeWindmill(FakeGoogle(), scripts_dir=str(SCRIPTS), sleep=slept.append)
    w.set_faults({"summarize_inbox": "slow:8"})
    status, raw = run(w, "summarize_inbox", OPS["summarize_inbox"])
    assert slept == [8.0] and status == 200
    assert json.loads(raw) is not None and w.calls[-1]["fault"] == "slow:8" and "result" in w.calls[-1]


def test_slow_fault_requires_numeric_seconds():
    w = FakeWindmill(FakeGoogle(), scripts_dir=str(SCRIPTS))
    for bad in ("slow", "slow:", "slow:abc"):
        with pytest.raises(ValueError):
            w.set_faults({"summarize_inbox": bad})


def test_default_timeout_sleep_exceeds_agent_timeouts():
    assert FakeWindmill(FakeGoogle(), scripts_dir=str(SCRIPTS)).timeout_sleep_sec > 180


def test_script_exception_is_windmill_500(wm):
    # list_calendars needs a resource dict; a bare string raises ValueError in the script
    status, raw = run(wm, "list_calendars", {"gcal": "gcal"})
    assert status == 500
    assert "ValueError" in json.loads(raw)["error"]["message"]


def test_unknown_script_and_endpoint(wm):
    assert run(wm, "nope", {})[0] == 404
    assert wm.handle("GET", "/api/w/evi/whatever")[0] == 404
    assert wm.handle("POST", RUN + "list_tasks", {}, b"{not json")[0] == 400


def test_async_webhook_returns_job_id_and_result(wm):
    status, body, _ = wm.handle("POST", ASYNC + "list_tasks", {}, json.dumps(OPS["list_tasks"]).encode())
    assert status == 201
    job_id = json.loads(body)
    s, b, _ = wm.handle("GET", f"/api/w/evi/jobs_u/completed/get_result/{job_id}")
    assert s == 200 and json.loads(b)["status"] == "ok"


def test_set_faults_rejects_unknown(wm):
    with pytest.raises(ValueError):
        wm.set_faults({"*": "gremlins"})


def test_does_not_patch_urllib_globally(wm):
    import urllib.request

    before = urllib.request.urlopen
    run(wm, "list_tasks", OPS["list_tasks"])
    assert urllib.request.urlopen is before


def test_starlette_app(wm):
    from starlette.testclient import TestClient

    c = TestClient(build_app(wm))
    r = c.post(RUN.rstrip("/") + "/list_tasks", json=OPS["list_tasks"])
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert c.post("/_sim/faults", json={"list_tasks": "http_500"}).status_code == 200
    assert c.post(RUN + "list_tasks", json=OPS["list_tasks"]).status_code == 500
    assert c.get("/_sim/calls").json()[-1]["fault"] == "http_500"
    assert c.post("/_sim/faults", json={"x": "bad"}).status_code == 400
    c.delete("/_sim/faults")
    assert c.post(RUN + "list_tasks", json=OPS["list_tasks"]).status_code == 200


def test_undeclared_payload_keys_are_dropped_like_real_windmill(wm, google):
    # the agent client always adds "action"; main() does not declare it
    payload = dict(OPS["schedule_event"], action="schedule_event", bogus=1)
    status, raw = run(wm, "schedule_event", payload)
    assert status == 200, raw
    assert [e["summary"] for e in google.state()["created"]["calendar"]] == ["Dentista"]
