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


# --- process_due_evaluations (needs_eval queue worker) ---------------------------

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=TZ)


class FakeQueue:
    def __init__(self, rows):
        self.rows = rows
        self.finished, self.bumped, self.extra = [], [], {}

    def list_stale_needs_eval(self, cutoff, limit=100):
        return [r for r in self.rows if r["msg_ts"] < cutoff]

    def list_promises_to_evaluate(self, now, limit=10):
        return [r for r in self.rows if r["next_eval_at"] <= now][:limit]

    def finish_promise_evaluation(self, rid, status, title=None, due_date=None, *, clear_due=False, confirmed_via=None):
        self.rows[:] = [r for r in self.rows if r["id"] != rid]
        self.finished.append((rid, status, title, due_date))
        self.extra[rid] = (clear_due, confirmed_via)
        return True

    def bump_promise_eval(self, rid, nxt):
        self.bumped.append((rid, nxt))
        return True


def qrow(rid, age_h=1.0, due=None, text="te mando a proposta amanhã", ready=True):
    ts = NOW - timedelta(hours=age_h)
    return {
        "id": rid, "source_id": f"m{rid}", "source_chat": JID, "raw_text": text,
        "msg_ts": ts, "created_at": ts, "due_date": due, "title": text,
        "next_eval_at": NOW - timedelta(minutes=1) if ready else NOW + timedelta(hours=1),
    }


@pytest.fixture
def queue(monkeypatch):
    import sys

    q = FakeQueue([])
    monkeypatch.setitem(sys.modules, "db", q)
    return q


def fake_eval(monkeypatch, result):
    def _ev(**kw):
        r = result(kw) if callable(result) else result
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(pc, "evaluate_promise", _ev)


def test_confirmed_becomes_pending_with_title_and_due(queue, monkeypatch):
    queue.rows[:] = [qrow(1)]
    fake_eval(monkeypatch, {"is_promise": True, "title": "Mandar a proposta", "due": "2026-10-13", "done": False})
    assert pc.process_due_evaluations(NOW)["pending"] == 1
    assert queue.finished == [(1, "pending", "Mandar a proposta", "2026-10-13")]


def test_confirmed_without_due_keeps_row_due(queue, monkeypatch):
    queue.rows[:] = [qrow(1, due="2026-10-13")]
    fake_eval(monkeypatch, {"is_promise": True, "title": "Mandar", "due": None, "done": False})
    pc.process_due_evaluations(NOW)
    assert queue.finished == [(1, "pending", "Mandar", None)]  # db keeps COALESCE(existing)


def test_rejected_becomes_dismissed(queue, monkeypatch):
    queue.rows[:] = [qrow(1)]
    fake_eval(monkeypatch, {"is_promise": False, "title": "", "due": None, "done": False})
    assert pc.process_due_evaluations(NOW)["dismissed"] == 1
    assert queue.finished[0][:2] == (1, "dismissed")
    assert queue.extra[1] == (False, "auto-eval")


def test_scn_debt_15_fulfilled_becomes_done(queue, monkeypatch):
    queue.rows[:] = [qrow(1)]
    fake_eval(monkeypatch, {"is_promise": True, "title": "x", "due": None, "done": True})
    assert pc.process_due_evaluations(NOW)["done"] == 1
    assert queue.finished[0][:2] == (1, "done")


def test_llm_none_before_48h_is_bumped_30min(queue, monkeypatch):
    queue.rows[:] = [qrow(1, age_h=2)]
    fake_eval(monkeypatch, None)
    assert pc.process_due_evaluations(NOW)["retry"] == 1
    assert queue.bumped == [(1, NOW + timedelta(minutes=30))] and queue.finished == []


def test_scn_debt_12_llm_none_after_48h_becomes_pending_original(queue, monkeypatch):
    queue.rows[:] = [qrow(1, age_h=49, due="2026-10-11")]
    fake_eval(monkeypatch, None)
    out = pc.process_due_evaluations(NOW)
    assert out["expired"] == 1
    assert queue.finished == [(1, "pending", None, None)]  # title untouched = original
    assert queue.extra[1] == (True, None)  # past due cleared so the row is listed


def test_stale_rows_finalized_even_when_not_due_for_eval(queue, monkeypatch):
    queue.rows[:] = [qrow(1, age_h=50, ready=False)]
    fake_eval(monkeypatch, AssertionError("llm must not be called"))
    assert pc.process_due_evaluations(NOW)["expired"] == 1
    assert queue.finished == [(1, "pending", None, None)]


def test_not_yet_due_rows_untouched(queue, monkeypatch):
    queue.rows[:] = [qrow(1, ready=False)]
    fake_eval(monkeypatch, AssertionError("llm must not be called"))
    out = pc.process_due_evaluations(NOW)
    assert not queue.finished and not queue.bumped and out["error"] == 0


def test_exception_in_one_row_does_not_stop_the_others(queue, monkeypatch):
    queue.rows[:] = [qrow(1, text="boom"), qrow(2)]
    fake_eval(
        monkeypatch,
        lambda kw: RuntimeError("x") if kw["message_text"] == "boom"
        else {"is_promise": True, "title": "T", "due": None, "done": False},
    )
    out = pc.process_due_evaluations(NOW)
    assert out["error"] == 1 and out["pending"] == 1
    assert queue.bumped == [(1, NOW + timedelta(minutes=30))]  # failing row not retried every tick
    assert queue.finished == [(2, "pending", "T", None)]


# --- daily sweep (SCN-DEBT-16) and re-evaluation (SCN-DEBT-13) -------------------


class FakeSweepDb:
    def __init__(self, rows):
        self.rows = rows
        self.swept, self.done, self.dismissed, self.updated = [], [], [], []

    def list_promises_to_sweep(self, now, limit=50, **kw):
        return list(self.rows)[:limit]

    def mark_promise_swept(self, rid, ts):
        self.swept.append(rid)
        return True

    def mark_promise_done_by_sweep(self, rid):
        self.done.append(rid)
        return True

    def list_pending_promises(self, limit=500):
        return list(self.rows)[:limit]

    def finish_pending_promise(self, rid, status, via):
        self.dismissed.append((rid, status, via))
        return True

    def update_pending_promise(self, rid, title, due, clear_due=False):
        self.updated.append((rid, title, due))
        return True


@pytest.fixture
def sdb(monkeypatch):
    import sys

    d = FakeSweepDb([])
    monkeypatch.setitem(sys.modules, "db", d)
    return d


def ctx(monkeypatch, after):
    monkeypatch.setattr(
        pc, "conversation_context",
        lambda jid, ts, **kw: {"contact": "Ana", "before": [], "after": after, "source": "evolution"},
    )


USER_AFTER = ["[22:00] Você: https://drive.google.com/x"]


def test_sweep_marks_done_when_fulfilled(sdb, monkeypatch):
    sdb.rows[:] = [qrow(1, age_h=20, text="Mandar o link do drive")]
    ctx(monkeypatch, USER_AFTER)
    fake_eval(monkeypatch, {"is_promise": True, "title": "x", "due": None, "done": True})
    c = pc.sweep_fulfilled(NOW)
    assert sdb.done == [1] and sdb.swept == [1]
    assert c["done"] == 1 and c["checked"] == 1


def test_sweep_skips_without_user_message_after_and_no_llm(sdb, monkeypatch):
    sdb.rows[:] = [qrow(1)]
    ctx(monkeypatch, ["[22:00] Ana: e aí?"])
    fake_eval(monkeypatch, lambda kw: pytest.fail("LLM must not be called"))
    c = pc.sweep_fulfilled(NOW)
    assert c["skipped"] == 1 and sdb.done == [] and sdb.swept == [1]


def test_sweep_none_is_error_and_not_marked_swept(sdb, monkeypatch):
    sdb.rows[:] = [qrow(1)]
    ctx(monkeypatch, USER_AFTER)
    fake_eval(monkeypatch, None)
    c = pc.sweep_fulfilled(NOW)
    assert c["error"] == 1 and sdb.done == [] and sdb.swept == []


def test_sweep_not_done_or_not_promise_is_unchanged(sdb, monkeypatch):
    sdb.rows[:] = [qrow(1), qrow(2)]
    ctx(monkeypatch, USER_AFTER)
    fake_eval(monkeypatch, lambda kw: {"is_promise": kw["message_id"] == "m1", "done": False,
                                       "title": "t", "due": None})
    c = pc.sweep_fulfilled(NOW)
    assert c["unchanged"] == 2 and sdb.done == [] and sdb.dismissed == [] and sdb.updated == []


def test_sweep_exception_in_row_does_not_stop_others(sdb, monkeypatch):
    sdb.rows[:] = [qrow(1), qrow(2)]
    ctx(monkeypatch, USER_AFTER)
    fake_eval(monkeypatch, lambda kw: RuntimeError("x") if kw["message_id"] == "m1"
              else {"is_promise": True, "done": True, "title": "t", "due": None})
    c = pc.sweep_fulfilled(NOW)
    assert c["error"] == 1 and sdb.done == [2]


def reeval_setup(sdb, monkeypatch, result):
    sdb.rows[:] = [qrow(1, text="Pode deixar")]
    fake_eval(monkeypatch, result)


def test_scn_debt_13_rejected_pending_is_dismissed_on_apply(sdb, monkeypatch):
    reeval_setup(sdb, monkeypatch, {"is_promise": False, "title": "", "due": None, "done": False})
    recs = pc.reevaluate_pending_promises(apply=False, now=NOW)
    assert recs[0]["decision"] == "dismiss" and sdb.dismissed == []  # dry-run changes nothing
    recs = pc.reevaluate_pending_promises(apply=True, now=NOW)
    assert recs[0]["decision"] == "dismiss" and sdb.dismissed == [(1, "dismissed", "auto-eval")]


def test_reeval_confirmed_gets_title_and_due(sdb, monkeypatch):
    reeval_setup(sdb, monkeypatch, {"is_promise": True, "title": "Mandar o orçamento", "due": "2026-10-16", "done": False})
    recs = pc.reevaluate_pending_promises(apply=True, now=NOW)
    assert recs[0]["decision"] == "update" and recs[0]["new_title"] == "Mandar o orçamento"
    assert sdb.updated == [(1, "Mandar o orçamento", "2026-10-16")]


def test_reeval_done_and_error_and_keep(sdb, monkeypatch):
    reeval_setup(sdb, monkeypatch, {"is_promise": True, "title": "", "due": None, "done": True})
    assert pc.reevaluate_pending_promises(apply=True, now=NOW)[0]["decision"] == "done"
    assert sdb.dismissed == [(1, "done", "auto-eval")]
    sdb.dismissed.clear()
    fake_eval(monkeypatch, None)
    assert pc.reevaluate_pending_promises(apply=True, now=NOW)[0]["decision"] == "error"
    fake_eval(monkeypatch, RuntimeError("boom"))
    assert pc.reevaluate_pending_promises(apply=True, now=NOW)[0]["decision"] == "error"
    fake_eval(monkeypatch, {"is_promise": True, "title": "Pode deixar", "due": None, "done": False})
    assert pc.reevaluate_pending_promises(apply=True, now=NOW)[0]["decision"] == "keep"
    assert sdb.dismissed == [] and sdb.updated == []
    assert "Pode deixar" in pc.format_reeval(pc.reevaluate_pending_promises(now=NOW))
