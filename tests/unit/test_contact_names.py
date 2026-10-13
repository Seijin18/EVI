"""SCN-NAME-01/03 — address-book sync through a faked Windmill response."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services import contact_names  # noqa: E402

_REGISTRY = [
    {"jid": "5511948260209@s.whatsapp.net", "display_name": None, "whatsapp_label": "+55 11 94826-0209"},
    {"jid": "5511900000001@s.whatsapp.net", "display_name": "Mina", "name_source": "user"},
]
_ENTRIES = [
    {"name": "Hollmann", "phones": ["(11) 4826-0209"]},
    {"name": "Outro Nome", "phones": ["11900000001"]},
]


def _run(response, *, dry_run=True, registry=_REGISTRY):
    integ = MagicMock()
    integ.post.return_value = response if isinstance(response, str) else json.dumps(response)
    with patch("integrations.factory.get_integration", return_value=integ), patch(
        "db.list_whatsapp_contacts_db", return_value=registry
    ), patch("db.upsert_whatsapp_contact") as up:
        return contact_names.sync(dry_run=dry_run), up, integ


def test_dry_run_reports_counts_and_writes_nothing():
    rep, up, integ = _run(_ENTRIES)
    assert rep["status"] == "ok" and rep["dry_run"] is True
    assert rep["new_names"] == 1 and rep["protected_user"] == 1
    up.assert_not_called()
    op, payload = integ.post.call_args.args
    assert op == "list_contacts" and payload == {"gcontacts": "$res:gcontacts"}
    assert "examples" not in rep, "counts only"


def test_apply_writes_agenda_source():
    rep, up, _ = _run(_ENTRIES, dry_run=False)
    assert rep["new_names"] == 1
    kw = up.call_args.kwargs
    assert kw["display_name"] == "Hollmann" and kw["name_source"] == "agenda"


def test_oauth_error_returns_oauth_status_and_writes_nothing():
    rep, up, _ = _run({"error": "reconnect", "reason": "oauth"}, dry_run=False)
    assert rep["status"] == "oauth"
    up.assert_not_called()


def test_transport_failure_is_an_error_status():
    rep, up, _ = _run("Windmill request failed: boom", dry_run=False)
    assert rep["status"] == "error"
    up.assert_not_called()


def test_disabled_flag_skips_the_call(monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_NAMES_SYNC_ENABLED", "false")
    with patch("integrations.factory.get_integration") as gi:
        assert contact_names.sync() == {"status": "disabled", "dry_run": True}
    gi.assert_not_called()


def test_endpoint_defaults_to_dry_run(monkeypatch):
    from fastapi.testclient import TestClient

    import main

    monkeypatch.setenv("EVI_CONTACT_NAMES_SYNC_ENABLED", "true")
    seen = {}
    monkeypatch.setattr(contact_names, "sync", lambda dry_run=True: seen.setdefault("d", dry_run) and {"status": "ok"})
    main.app.dependency_overrides[main.verify_api_key] = lambda: None
    try:
        TestClient(main.app).post("/jobs/contact-names-sync")
    finally:
        main.app.dependency_overrides.clear()
    assert seen["d"] is True
