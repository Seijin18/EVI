"""promise_context: conversation window, prompt v4 and evaluate_promise post-processing."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from services import promise_context as pc

TZ = ZoneInfo("America/Sao_Paulo")
REF = datetime(2026, 10, 12, 14, 0, tzinfo=TZ)  # Monday
JID = "5511999990000@s.whatsapp.net"


def msg(mid, ts, text, me=False):
    return SimpleNamespace(id=mid, ts=ts.isoformat(), text=text, from_me=me)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    monkeypatch.setattr(pc, "_contact_name", lambda jid: "Ana")


def use_msgs(monkeypatch, msgs):
    monkeypatch.setattr(pc, "_fetch_messages", lambda jid: msgs)


def llm(monkeypatch, out, seen=None):
    def fake(task, prompt, schema, **kw):
        if seen is not None:
            seen.append(prompt)
        return out

    monkeypatch.setattr(pc.llm_structured, "run_structured", fake)


def test_promise_orcamento_due_friday(monkeypatch):
    use_msgs(monkeypatch, [
        msg("a", REF - timedelta(minutes=2), "consegue me mandar o orçamento até sexta?"),
        msg("b", REF, "Pode deixar", me=True),
    ])
    seen = []
    llm(monkeypatch, {"pedido": "mandar o orçamento até sexta", "usuario_se_compromete": True,
                      "what": "Mandar o orçamento", "quando": "até sexta", "done": False}, seen)
    r = pc.evaluate_promise(JID, "Pode deixar", REF, message_id="b", now=REF + timedelta(minutes=5))
    assert r["is_promise"] and "orçamento" in r["title"]
    assert r["due"] == "2026-10-16"
    assert r["done"] is False and r["prompt_version"] == "v4"
    assert "«externo:whatsapp»" in seen[0] and "consegue me mandar o orçamento" in seen[0]
    assert "segunda, 2026-10-12" in seen[0]


def test_not_promise_and_generic_what(monkeypatch):
    use_msgs(monkeypatch, [])
    llm(monkeypatch, {"pedido": "", "usuario_se_compromete": False, "what": "", "quando": "", "done": False})
    assert pc.evaluate_promise(JID, "Pode deixar, qualquer coisa te aviso", REF)["is_promise"] is False
    for what in ("Avisar", "avisar te", "Responder"):
        llm(monkeypatch, {"pedido": "", "usuario_se_compromete": True, "what": what, "quando": "", "done": False})
        assert pc.evaluate_promise(JID, "te aviso", REF)["is_promise"] is False


def test_done_from_after_block(monkeypatch):
    use_msgs(monkeypatch, [
        msg("a", REF - timedelta(minutes=1), "me passa o contato do eletricista?"),
        msg("b", REF, "Já te passo", me=True),
        msg("c", REF + timedelta(minutes=2), "11 98888-7777", me=True),
    ])
    seen = []
    llm(monkeypatch, {"pedido": "passar o contato", "usuario_se_compromete": True,
                      "what": "passar o contato do eletricista", "quando": "", "done": True}, seen)
    r = pc.evaluate_promise(JID, "Já te passo", REF, message_id="b", now=REF + timedelta(minutes=10))
    assert r["is_promise"] and r["done"] is True
    assert "[14:02] Você: 11 98888-7777" in seen[0]
    assert r["title"][0].isupper()


def test_context_window_and_wrapping(monkeypatch):
    msgs = [msg("old", REF - timedelta(hours=25), "muito antigo")]
    msgs += [msg(f"m{i}", REF - timedelta(minutes=60 - i), f"msg {i}") for i in range(12)]
    msgs += [msg("me", REF, "Pode deixar", me=True),
             msg("fut", REF + timedelta(hours=3), "depois do now")]
    use_msgs(monkeypatch, msgs)
    ctx = pc.conversation_context(JID, REF, message_id="me", now=REF + timedelta(minutes=30))
    assert ctx["source"] == "evolution" and ctx["contact"] == "Ana"
    assert len(ctx["before"]) == 10
    assert ctx["before"][-1].endswith("msg 11 «/externo»")
    assert all("Pode deixar" not in ln and "muito antigo" not in ln for ln in ctx["before"])
    assert ctx["after"] == []
    assert ctx["before"][0].startswith("[13:02] Ana: «externo:whatsapp»")


def test_user_text_not_wrapped_and_exclusion_without_id(monkeypatch):
    use_msgs(monkeypatch, [msg("x", REF, "Pode deixar", me=True),
                           msg("y", REF + timedelta(minutes=1), "feito", me=True)])
    ctx = pc.conversation_context(JID, REF, now=REF + timedelta(minutes=5))
    assert ctx["after"] == ["[14:01] Você: feito"]
    assert ctx["before"] == []


def test_timeline_fallback_and_none(monkeypatch):
    monkeypatch.setattr(pc, "_fetch_messages", lambda jid: None)
    import services.contact_filesystem as cf
    monkeypatch.setattr(cf, "read_timeline_tail", lambda jid, n: [
        {"ts": (REF - timedelta(hours=1)).isoformat(), "text_preview": "[Ana] oi tudo bem"},
        {"ts": (REF - timedelta(minutes=30)).isoformat(), "text_preview": "[eu] respondi"},
    ])
    ctx = pc.conversation_context(JID, REF, now=REF)
    assert ctx["source"] == "timeline" and len(ctx["before"]) == 1
    assert "oi tudo bem" in ctx["before"][0]
    monkeypatch.setattr(cf, "read_timeline_tail", lambda jid, n: [])
    assert pc.conversation_context(JID, REF, now=REF)["source"] == "none"


def test_evolution_exception_and_llm_none(monkeypatch):
    import messaging.evolution as ev

    def boom(self, *a, **k):
        raise OSError("down")

    monkeypatch.setattr(ev.EvolutionClient, "find_messages", boom)
    import services.contact_filesystem as cf
    monkeypatch.setattr(cf, "read_timeline_tail", lambda jid, n: [])
    assert pc.conversation_context(JID, REF, now=REF)["source"] == "none"
    llm(monkeypatch, None)
    assert pc.evaluate_promise(JID, "ok", REF) is None


def test_knowledge_block():
    p = pc.build_promise_prompt("Ana", [], "oi", "12/10 14:00", [], REF, knowledge="Irmã do usuário")
    assert p.startswith("SOBRE Ana:\nIrmã do usuário")
    assert "(nada)" in p
