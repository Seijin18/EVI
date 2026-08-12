"""SCN-AUTH-02/03 — every mutating route is gated when EVI_API_KEY is set."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from auth import (  # noqa: E402
    api_key_required,
    require_api_key_configured,
    verify_api_key,
)
from fastapi import HTTPException  # noqa: E402

_KEY = "s3cret"

# Routes that must 401 without a key. `/` and `/health` stay open on purpose:
# the compose healthcheck hits `/` and a Prometheus scrape cannot send a header.
PROTECTED = [
    ("get", "/tools", None),
    ("post", "/reset", {}),
    ("post", "/note", {"title": "t", "content": "c"}),
    ("post", "/insight", {}),
    ("post", "/chat", {"message": "hi"}),
    ("post", "/run-task", {"task": "nope", "params": {}}),
    ("post", "/jobs/daily-summary", {}),
    ("post", "/jobs/heartbeat", {}),
    ("post", "/jobs/contact-learn", {}),
    ("post", "/webhooks/telegram", {"message": {}}),
    ("post", "/webhooks/evolution", {}),
]

OPEN = [("get", "/"), ("get", "/health")]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("EVI_API_KEY", _KEY)
    main.app_state.graph = MagicMock()
    return TestClient(main.app)


def _call(client, method, path, body):
    fn = getattr(client, method)
    return fn(path) if body is None else fn(path, json=body)


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_protected_route_rejects_missing_key(client, method, path, body):
    assert _call(client, method, path, body).status_code == 401


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_protected_route_rejects_wrong_key(client, method, path, body):
    fn = getattr(client, method)
    kwargs = {"headers": {"X-Api-Key": "wrong"}}
    if body is not None:
        kwargs["json"] = body
    assert fn(path, **kwargs).status_code == 401


@pytest.mark.parametrize("method,path", OPEN)
def test_open_routes_stay_reachable(client, method, path):
    """Healthcheck and scrape paths must not need a header."""
    assert getattr(client, method)(path).status_code == 200


def test_correct_key_is_accepted(client):
    with patch("services.context_assembly.build_context", return_value=""):
        r = client.get("/tools", headers={"X-Api-Key": _KEY})
    assert r.status_code == 200
    assert "tools" in r.json()


def test_no_key_configured_leaves_routes_open(monkeypatch):
    """Backward compatible: empty EVI_API_KEY keeps the local setup working."""
    monkeypatch.setenv("EVI_API_KEY", "")
    main.app_state.graph = MagicMock()
    assert TestClient(main.app).get("/tools").status_code == 200


def test_verify_api_key_directly(monkeypatch):
    monkeypatch.setenv("EVI_API_KEY", _KEY)
    assert verify_api_key(_KEY) is None
    with pytest.raises(HTTPException) as exc:
        verify_api_key(None)
    assert exc.value.status_code == 401


def test_require_api_key_configured_blocks_startup(monkeypatch):
    monkeypatch.setenv("EVI_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("EVI_API_KEY", "")
    assert api_key_required() is True
    with pytest.raises(RuntimeError, match="EVI_REQUIRE_API_KEY"):
        require_api_key_configured()


def test_require_api_key_configured_passes_when_set(monkeypatch):
    monkeypatch.setenv("EVI_REQUIRE_API_KEY", "true")
    monkeypatch.setenv("EVI_API_KEY", _KEY)
    require_api_key_configured()


def test_enforcement_is_off_by_default(monkeypatch):
    monkeypatch.delenv("EVI_REQUIRE_API_KEY", raising=False)
    monkeypatch.setenv("EVI_API_KEY", "")
    assert api_key_required() is False
    require_api_key_configured()
