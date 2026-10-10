"""SCN-INJ-01/02: two-step e-mail deletion verified in code."""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from services import turn_log, write_guard  # noqa: E402
from services.untrusted import wrap_external  # noqa: E402
from tools.email_tool import delete_emails, delete_emails_by_query  # noqa: E402

SID = "tg-123"
DRY = json.dumps(
    {
        "status": "ok",
        "count": 7,
        "messages": [
            {"id": f"m{i}", "subject": f"Promo {i}", "from": "loja@x.com"} for i in range(7)
        ],
    }
)
DELETED = '{"status":"ok","deleted":%d}'


@pytest.fixture
def env(monkeypatch):
    rows: list[dict] = []
    import db

    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(
        db, "save_tool_snapshot", lambda sid, name, payload: rows.insert(0, {"sid": sid, "tool_name": name, "payload": payload})
    )
    monkeypatch.setattr(
        db,
        "load_tool_snapshots",
        lambda sid, limit=5: [r for r in rows if r["sid"] == sid][:limit],
    )
    client = MagicMock()
    posts: list[tuple[str, dict]] = []

    def post(op, payload, **kw):
        posts.append((op, payload))
        if op == "search_emails":
            return DRY
        return DELETED % len(payload["message_ids"])

    client.post.side_effect = post
    monkeypatch.setattr("tools.email_tool.get_integration", lambda: client)

    class Env:
        pass

    e = Env()
    e.rows, e.posts = rows, posts

    def turn(text, session=SID):
        if getattr(e, "_tok", None) is not None:
            turn_log.end_turn(e._tok)  # the previous turn completed
        _, token = turn_log.start_turn("telegram", session, user_text=text)
        e._tok = token

    e._tok = None

    def seed_inbox(ids, session=SID):
        raw = "\n".join(
            f"• [{i}] " + wrap_external(f"De: a — Assunto: Mail {i}", "email") for i in ids
        )
        rows.insert(0, {"sid": session, "tool_name": "summarize_inbox", "payload": {"raw": raw}})

    e.seed_inbox = seed_inbox

    e.turn = turn
    e.deletes = lambda: [p for p in posts if p[0] == "delete_emails"]
    yield e
    turn_log._current.set(None)


def _token(out: str) -> str:
    return out.split("token: ")[1].rstrip(")").strip()


def test_is_confirmation():
    for ok in [
        "sim", "Sim!", "s", "confirma", "Pode apagar", "Confirmo", "manda ver", "pode sim",
        "sim, pode apagar", "ok pode apagar", "sim pode", "sim por favor", "pode apagar pfv",
    ]:
        assert write_guard.is_confirmation(ok), ok
    for bad in [
        "não, espera", "nao", "sim, não", "cancela", "ok", "", "bom dia", "x" * 80 + " sim",
        "pode", "apaga", "pode ser depois", "pode parar", "pode me lembrar amanhã?",
        "pode marcar reunião às 15h", "sim, mas só os de ontem", "apaga só o primeiro",
        'ele disse "sim"', "sim sim", "sim pode apagar tudo agora mesmo ok",
    ]:
        assert not write_guard.is_confirmation(bad), bad


def test_non_ascii_token_never_raises(env):
    env.turn("apague as promoções")
    delete_emails_by_query.invoke({"q": "category:promotions"})
    env.turn("sim")
    out = delete_emails.invoke({"message_ids": [], "confirm_token": "tóken-ñ"})
    assert "desconhecido" in out and env.deletes() == []


def test_first_call_never_deletes_and_same_turn_confirm_refused(env):
    env.turn("apague as promoções")
    out = delete_emails_by_query.invoke({"q": "category:promotions"})
    assert "Vou mover 7" in out and "«externo:email»" in out and "+2 outros" in out
    assert env.deletes() == []
    # query was sent as dry run
    assert env.posts[0][0] == "search_emails"
    tok = _token(out)
    # same turn: even a "sim" in the same user text is refused
    refused = delete_emails_by_query.invoke({"q": "", "confirm_token": tok})
    assert "NÃO executada" in refused and "nova mensagem" in refused
    assert env.deletes() == []


def test_next_turn_sim_deletes_exactly_stored_ids(env):
    env.turn("apague as promoções")
    tok = _token(delete_emails_by_query.invoke({"q": "category:promotions"}))
    env.turn("sim")
    out = delete_emails_by_query.invoke({"q": "outra coisa", "confirm_token": tok})
    assert "7 email(s)" in out
    assert env.deletes() == [("delete_emails", {"message_ids": [f"m{i}" for i in range(7)], "gmail": env.deletes()[0][1]["gmail"]})]
    # token consumed
    env.turn("sim")
    again = delete_emails.invoke({"message_ids": ["x"], "confirm_token": tok})
    assert "NÃO executada" in again and len(env.deletes()) == 1


def test_injected_email_then_ok_deletes_nothing(env):
    # user asked only for a summary; an email says "apague tudo"; the model has no token
    env.turn("resuma minha caixa")
    env.turn("ok")
    out = delete_emails.invoke({"message_ids": ["m1"], "confirm_token": "invented"})
    assert "NÃO executada" in out and "pendente" in out
    assert env.deletes() == []


def test_injected_email_first_call_then_ok_not_a_confirmation(env):
    env.turn("apague os e-mails m1 e m2")
    env.seed_inbox(["m1", "m2"])
    out = delete_emails.invoke({"message_ids": ["m1", "m2"]})
    tok = _token(out)
    env.turn("ok")  # "ok" alone is not in the confirmation list
    refused = delete_emails.invoke({"message_ids": [], "confirm_token": tok})
    assert "explícita" in refused and env.deletes() == []


def test_negation_expired_wrong_token_and_other_session(env):
    env.seed_inbox(["a", "b"])
    env.turn("apague")
    tok = _token(delete_emails.invoke({"message_ids": ["a", "b"]}))
    env.turn("não, espera")
    assert "NÃO executada" in delete_emails.invoke({"message_ids": [], "confirm_token": tok})
    # pending was cleared at the end of that turn: a later "sim" has nothing to confirm
    env.turn("sim")
    assert "pendente" in delete_emails.invoke({"message_ids": [], "confirm_token": tok})
    env.turn("apague")
    tok = _token(delete_emails.invoke({"message_ids": ["a", "b"]}))
    env.turn("sim")
    assert "desconhecido" in delete_emails.invoke({"message_ids": [], "confirm_token": "zzz"})
    env.turn("sim", session="tg-other")
    assert "pendente" in delete_emails.invoke({"message_ids": [], "confirm_token": tok})
    env.turn("apague")
    tok = _token(delete_emails.invoke({"message_ids": ["a", "b"]}))
    env.turn("sim")
    env.rows[0]["payload"]["expires_at"] = time.time() - 1
    assert "expirou" in delete_emails.invoke({"message_ids": [], "confirm_token": tok})
    assert env.deletes() == []


def test_confirmation_two_turns_later_is_refused(env):
    env.turn("apague as promoções")
    tok = _token(delete_emails_by_query.invoke({"q": "category:promotions"}))
    env.turn("que horas são?")
    env.turn("sim")
    out = delete_emails.invoke({"message_ids": [], "confirm_token": tok})
    assert "NÃO executada" in out and env.deletes() == []


def test_staging_without_delete_intent_is_refused(env):
    env.turn("resume meus e-mails")
    out = delete_emails_by_query.invoke({"q": "category:promotions"})
    assert out == write_guard.NO_INTENT_MESSAGE and env.rows == []
    env.seed_inbox(["m1"])
    assert delete_emails.invoke({"message_ids": ["m1"]}) == write_guard.NO_INTENT_MESSAGE


def test_unknown_ids_refused_never_staged_blind(env):
    env.seed_inbox(["m1"])
    env.turn("apague os e-mails")
    out = delete_emails.invoke({"message_ids": ["m1", "ghost"]})
    assert "Não reconheço" in out
    assert all(r["tool_name"] != write_guard.PENDING_TOOL for r in env.rows)


def test_staging_records_preview_for_main(env):
    env.turn("apague as promoções")
    delete_emails_by_query.invoke({"q": "category:promotions"})
    pend = turn_log.pending_created_this_turn()
    assert pend["count"] == 7 and len(pend["subjects"]) == 5


def test_no_turn_context_refuses(env):
    out = delete_emails.invoke({"message_ids": ["a"]})
    assert "fora de uma conversa" in out and env.deletes() == []


def test_max_messages_clamped_to_50(env):
    env.turn("apague")
    delete_emails_by_query.invoke({"q": "x", "max_messages": 500})
    assert env.posts[0][1]["max_messages"] == 50
    ids = [f"i{n}" for n in range(80)]
    env.seed_inbox(ids)
    out = delete_emails.invoke({"message_ids": ids})
    assert "Vou mover 50" in out
    assert len(env.rows[0]["payload"]["ids"]) == 50


def test_old_windmill_without_search_op_refuses_and_never_deletes(env, monkeypatch):
    client = MagicMock()
    client.post.return_value = "Windmill request failed: 404 Script not found"
    monkeypatch.setattr("tools.email_tool.get_integration", lambda: client)
    env.turn("apague")
    out = delete_emails_by_query.invoke({"q": "x"})
    assert "indisponível" in out and env.rows == []
    assert [c[0][0] for c in client.post.call_args_list] == ["search_emails"]


def test_turn_seq_strictly_increases():
    seqs = []
    for _ in range(3):
        c, t = turn_log.start_turn("api", "s", user_text="u")
        seqs.append(turn_log.current_turn_seq())
        assert turn_log.current_user_text() == "u"
        turn_log.end_turn(t)
    assert seqs == sorted(set(seqs))
