"""SCN-NAME-01: list_contacts follows People API pagination and leaks only name + phones."""

import importlib.util
import json
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "windmill/f/integrations/list_contacts.py"
FIXTURE = ROOT / "tests/fixtures/google/people_connections.json"


def _load():
    spec = importlib.util.spec_from_file_location("wm_list_contacts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _patch_pages(monkeypatch, mod, calls):
    pages = json.loads(FIXTURE.read_text(encoding="utf-8"))["pages"]

    def fake(token, page_token):
        calls.append((token, page_token))
        return pages[0] if page_token is None else pages[1]

    monkeypatch.setattr(mod, "_fetch_page", fake)


def test_two_pages_only_name_and_phones(monkeypatch):
    mod = _load()
    calls = []
    _patch_pages(monkeypatch, mod, calls)
    out = mod.main({"token": "tok"})
    assert calls == [("tok", None), ("tok", "TOKEN_PAGE_2")]
    assert out == [
        {"name": "Joana Álvares", "phones": ["+55 11 91234-0001", "(11) 91234-0001"]},
        {"name": "João Conceição", "phones": ["+55 21 97777-0004"]},
    ]
    for entry in out:
        assert set(entry) == {"name", "phones"}


def test_no_other_field_leaks(monkeypatch):
    mod = _load()
    _patch_pages(monkeypatch, mod, [])
    blob = json.dumps(mod.main({"token": "tok"}), ensure_ascii=False)
    for leaked in ("example.invalid", "Rua Ficticia", "photo", "nota privada",
                   "Empresa", "resourceName", "etag", "Sem Telefone"):
        assert leaked not in blob


def _raising(code):
    def fake(token, page_token):
        raise urllib.error.HTTPError("u", code, "x", {}, None)

    return fake


def test_401_and_403_are_oauth(monkeypatch):
    mod = _load()
    for code in (401, 403):
        monkeypatch.setattr(mod, "_fetch_page", _raising(code))
        out = mod.main({"token": "tok"})
        assert out["reason"] == "oauth" and out["error"]
        assert set(out) == {"error", "reason"}


def test_network_error_is_upstream(monkeypatch):
    mod = _load()

    def boom(token, page_token):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(mod, "_fetch_page", boom)
    assert mod.main({"token": "tok"})["reason"] == "upstream_error"
    monkeypatch.setattr(mod, "_fetch_page", _raising(500))
    assert mod.main({"token": "tok"})["reason"] == "upstream_error"


def test_page_cap(monkeypatch):
    mod = _load()
    n = []

    def endless(token, page_token):
        n.append(1)
        return {"connections": [], "nextPageToken": "again"}

    monkeypatch.setattr(mod, "_fetch_page", endless)
    assert mod.main({"token": "tok"}) == []
    assert len(n) == 20
