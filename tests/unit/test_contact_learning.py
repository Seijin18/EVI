"""learn_contact drives the structured knowledge update by jid (no appended synthesis)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services import contact_filesystem as cf
from services import contact_knowledge as ck
from services import contact_learning as cl

JID = "5516992657231@s.whatsapp.net"


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(cl, "resolve_contact_for_query", lambda q: ((JID, "Leozao"), ""))
    return tmp_path


def _msg(text="trabalho na Acme"):
    when = datetime.now(timezone.utc) - timedelta(hours=1)
    cf.append_timeline(JID, source_id="m1", text_preview=f"[Leozao] {text}", ts=when.isoformat(), label="Leozao")
    return when.astimezone(ck._tz()).strftime("%Y-%m-%d")


def test_learn_contact_updates_knowledge_by_jid(mem, monkeypatch):
    day = _msg()
    seen = {}

    def fake(jid):
        seen["jid"] = jid
        return real(jid)

    real = ck.update_contact_knowledge
    monkeypatch.setattr(cl, "update_contact_knowledge", fake)
    monkeypatch.setattr(
        "services.llm_structured.run_structured",
        lambda *a, **k: {"add": [{"fact": "Trabalha na Acme", "date": day}], "remove": [], "open": []},
    )
    out = cl.learn_contact("Leozao", fetch_messages=False)
    assert seen["jid"] == JID
    assert "atualizado" in out and "+1 fato" in out and "Trabalha na Acme" in out
    text = (mem / "contacts" / JID / "profile.md").read_text(encoding="utf-8")
    assert "## Síntese" not in text and f"- Trabalha na Acme ({day})" in text


def test_learn_contact_without_new_messages(mem, monkeypatch):
    called = []
    monkeypatch.setattr("services.llm_structured.run_structured", lambda *a, **k: called.append(1))
    out = cl.learn_contact("Leozao", fetch_messages=False)
    assert out.startswith("Não há mensagens novas") and called == []


def test_learn_contact_llm_failure_reports_and_keeps_profile(mem, monkeypatch):
    _msg()
    cf.ensure_contact(JID, label="Leozao")
    p = mem / "contacts" / JID / "profile.md"
    before = p.read_bytes()
    monkeypatch.setattr("services.llm_structured.run_structured", lambda *a, **k: None)
    out = cl.learn_contact("Leozao", fetch_messages=False)
    assert out.startswith("Não consegui atualizar") and p.read_bytes() == before
