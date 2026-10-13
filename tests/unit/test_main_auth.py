"""SCN-AUTH-01 — with enforcement on, every non-public route answers 401 without a key."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

_KEY = "k" * 32


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("EVI_API_KEY", _KEY)
    monkeypatch.setenv("EVI_REQUIRE_API_KEY", "true")
    main.app_state.graph = MagicMock()
    return TestClient(main.app)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/tools", None),
        ("get", "/metrics", None),
        ("post", "/chat", {"message": "hi"}),
        ("post", "/run-task", {"task": "x", "params": {}}),
        ("post", "/jobs/daily-summary", {}),
        ("post", "/jobs/heartbeat", {}),
        ("post", "/jobs/contact-learn", {}),
    ],
)
def test_401_without_key(client, method, path, body):
    fn = getattr(client, method)
    r = fn(path) if body is None else fn(path, json=body)
    assert r.status_code == 401


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_metrics_with_key_labels_by_route_template(client, monkeypatch):
    monkeypatch.setenv("EVI_METRICS_ENABLED", "true")
    client.get("/definitely/not/a/route/12345")
    r = client.get("/metrics", headers={"X-Api-Key": _KEY})
    assert r.status_code == 200
    assert "12345" not in r.text, "raw URL path must not become a label"
    assert 'path="unmatched"' in r.text


def test_contact_learn_job_runs_in_background_unless_wait(client, monkeypatch):
    import services.contact_learn_cron as cron

    monkeypatch.setattr(cron, "run_contact_learn_batch", lambda: {"ok": True, "updated": 3})
    hdr = {"X-Api-Key": _KEY}
    accepted = client.post("/jobs/contact-learn", headers=hdr)
    assert accepted.status_code == 200 and accepted.json()["status"] in {"accepted", "already_running"}
    inline = client.post("/jobs/contact-learn?wait=true", headers=hdr)
    assert inline.json() in ({"ok": True, "updated": 3}, {"status": "already_running", "job": "contact-learn"})
