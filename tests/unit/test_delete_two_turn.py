"""SCN-INJ: e-mail deletion across real turns through main._chat_impl.

A fake graph plays the model: it calls the REAL delete tools, so the preview
appended by code, the "next message only" rule and the intent check are exercised
end to end (no network, no DB: the snapshot table is faked in memory).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

import main  # noqa: E402
from services.session_memory import reset_for_tests  # noqa: E402
from services.untrusted import wrap_external  # noqa: E402
from tools.email_tool import delete_emails  # noqa: E402

SID = "telegram-777"
IDS = [f"id{i}" for i in range(7)]


class FakeGraph:
    """Turn script: text -> callable(state) returning the model's final reply."""

    def __init__(self):
        self.token = ""
        self.script = {}

    def invoke(self, state, config=None):
        text = state["messages"][-1].content
        reply = self.script.get(text, lambda: "ok")()
        return {"messages": [AIMessage(content=reply)], "final_answer": reply}


@pytest.fixture
def env(monkeypatch):
    import db

    rows: list[dict] = []
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EVI_API_KEY", "")
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(
        db, "save_tool_snapshot",
        lambda sid, name, payload: rows.insert(0, {"sid": sid, "tool_name": name, "payload": payload}),
    )
    monkeypatch.setattr(
        db, "load_tool_snapshots", lambda sid, limit=5: [r for r in rows if r["sid"] == sid][:limit]
    )
    raw = "\n".join(
        f"• [{i}] " + wrap_external(f"De: x — Assunto: Promo {i}", "email") for i in IDS
    )
    rows.append({"sid": SID, "tool_name": "summarize_inbox", "payload": {"raw": raw}})
    client = MagicMock()
    posts = []

    def post(op, payload, **kw):
        posts.append((op, payload))
        return '{"status":"ok","deleted":%d}' % len(payload.get("message_ids", []))

    client.post.side_effect = post
    monkeypatch.setattr("tools.email_tool.get_integration", lambda: client)
    graph = FakeGraph()
    main.app_state.graph = graph
    reset_for_tests()

    class E:
        pass

    e = E()
    e.graph, e.rows, e.posts = graph, rows, posts
    e.say = lambda text: main._chat_impl(main.ChatRequest(message=text), SID, "telegram")["response"]
    e.deleted = lambda: [p[1]["message_ids"] for p in posts if p[0] == "delete_emails"]
    e.pending = lambda: next(
        r["payload"] for r in rows if r["tool_name"] == "pending_delete"
    )
    return e


def _stage(e, ids=IDS):
    def run():
        out = delete_emails.invoke({"message_ids": ids})
        e.token = out.split("token: ")[1].rstrip(")").strip()
        return "Vou apagar, ok?"  # the model's own text says nothing useful

    return run


def _confirm(e):
    return lambda: delete_emails.invoke({"message_ids": [], "confirm_token": e.token})


def test_stage_then_sim_deletes_exactly_the_staged_ids(env):
    env.graph.script = {"apaga as promoções": _stage(env), "sim": _confirm(env)}
    reply = env.say("apaga as promoções")
    assert reply.startswith("Vou apagar, ok?")
    assert "🗑️ Vou mover 7 e-mail(s) para a lixeira:" in reply
    assert reply.count("«externo:email»") == 5 and "… e mais 2 outros" in reply
    assert reply.rstrip().endswith("Responda «sim» para confirmar.")
    assert env.deleted() == []
    out = env.say("sim")
    assert "7 email(s)" in out
    assert env.deleted() == [IDS]


def test_unrelated_turn_in_between_kills_the_pending(env):
    env.graph.script = {"apaga as promoções": _stage(env), "sim": _confirm(env)}
    env.say("apaga as promoções")
    env.say("que horas são?")
    assert env.pending().get("cleared") is True
    out = env.say("sim")
    assert "NÃO executada" in out
    assert env.deleted() == []


def test_injected_staging_without_user_intent_is_refused(env):
    env.graph.script = {"resume meus e-mails": _stage_expect_refusal(env)}
    reply = env.say("resume meus e-mails")
    assert "Só apago e-mails quando você pede." in reply
    assert "🗑️" not in reply
    assert not any(r["tool_name"] == "pending_delete" for r in env.rows)
    assert env.deleted() == []


def _stage_expect_refusal(e):
    return lambda: delete_emails.invoke({"message_ids": IDS})


def test_forwarded_message_cannot_confirm(env):
    env.graph.script = {"apaga as promoções": _stage(env), "sim": _confirm(env)}
    env.say("apaga as promoções")
    out = main._chat_impl(main.ChatRequest(message="sim"), SID, "telegram", forwarded=True)
    assert "NÃO executada" in out["response"]
    assert env.deleted() == []


