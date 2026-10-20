"""SCN-PREC-04/05 — LLM debt judge: verdict stored out of band, list_debts never calls an LLM."""

from datetime import datetime, timedelta, timezone

import pytest

from services import debt_judge as dj
from services import reply_debts as rd

JID = "5511999990000@s.whatsapp.net"
NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)


class FakeDb:
    """In-memory wa_conversation_state with the real set_debt_verdict semantics."""

    def __init__(self):
        self.rows = {}

    def add(self, jid=JID, preview="o contrato está pronto", in_id="m1", hours=6, out_at=None):
        self.rows[jid] = {
            "jid": jid, "last_in_at": NOW - timedelta(hours=hours), "last_in_preview": preview,
            "last_in_id": in_id, "last_out_at": out_at, "last_out_preview": None,
            "judge_in_id": None, "judge_needs_reply": None, "judge_at": None,
        }

    def init_db(self):
        pass

    def list_debt_candidates(self, now, min_age, max_age, limit=200):
        return [dict(r) for r in self.rows.values()
                if now - max_age <= r["last_in_at"] <= now - min_age]

    def set_debt_verdict(self, jid, in_id, needs_reply):
        r = self.rows.get(jid)
        if not r or r["last_in_id"] != in_id:
            return False
        r.update(judge_in_id=in_id, judge_needs_reply=needs_reply, judge_at=NOW)
        return True

    def get_whatsapp_contact(self, jid):
        return None

    def list_states(self):
        return []

    def new_inbound(self, jid, in_id, preview):
        self.rows[jid].update(last_in_id=in_id, last_in_preview=preview)


@pytest.fixture
def env(monkeypatch):
    import db

    fake = FakeDb()
    for name in ("init_db", "list_debt_candidates", "set_debt_verdict", "get_whatsapp_contact", "list_states"):
        monkeypatch.setattr(db, name, getattr(fake, name))
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/fake")
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    monkeypatch.delenv("EVI_DEBT_JUDGE", raising=False)
    dj._backoff.clear()
    monkeypatch.setattr(dj, "_context_lines", lambda jid, row, now: ["[10:00] Usuário: oi"])
    return fake


def llm(monkeypatch, out, calls):
    def fake(task, prompt, schema, **kw):
        calls.append((task, prompt))
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(dj.llm_structured, "run_structured", fake)


def listed(now=NOW):
    return [d["jid"] for d in rd.list_debts(now=now)]


def test_prec04_verdict_false_hides_and_list_never_calls_llm(env, monkeypatch):
    env.add()
    calls = []
    llm(monkeypatch, {"needs_reply": False, "reason": "informa"}, calls)
    assert listed() == [JID]  # no verdict yet: fail-safe
    assert dj.judge_candidates(now=NOW) == 1
    assert len(calls) == 1 and calls[0][0] == "DEBT"
    assert listed() == []
    assert listed() == []
    assert len(calls) == 1  # list_debts made zero LLM calls
    assert dj.judge_candidates(now=NOW) == 0 and len(calls) == 1  # valid verdict: not re-judged


def test_prec04_new_inbound_invalidates_verdict(env, monkeypatch):
    env.add()
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, [])
    dj.judge_candidates(now=NOW)
    assert listed() == []
    env.new_inbound(JID, "m2", "o contrato está pronto")
    assert listed() == [JID]
    assert env.set_debt_verdict(JID, "m1", False) is False  # stale id never writes


def test_verdict_true_keeps_listed(env, monkeypatch):
    env.add()
    llm(monkeypatch, {"needs_reply": True, "reason": "x"}, [])
    assert dj.judge_candidates(now=NOW) == 1
    assert listed() == [JID]


@pytest.mark.parametrize("out", [RuntimeError("cap"), None, {"reason": "x"}, {"needs_reply": "false"}])
def test_prec05_failure_stores_nothing(env, monkeypatch, out):
    env.add()
    llm(monkeypatch, out, [])
    assert dj.judge_candidates(now=NOW) == 0
    assert env.rows[JID]["judge_in_id"] is None
    assert listed() == [JID]


@pytest.mark.parametrize("preview", ["me manda o contrato", "chegou o contrato?", "valeu!", "ok"])
def test_clear_request_and_closing_never_judged(env, monkeypatch, preview):
    env.add(preview=preview)
    calls = []
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, calls)
    assert dj.judge_candidates(now=NOW) == 0
    assert calls == []


def test_acknowledgement_never_judged(env, monkeypatch):
    env.add(preview="vou ver isso", hours=6, out_at=NOW - timedelta(hours=6, minutes=2))
    calls = []
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, calls)
    assert dj.judge_candidates(now=NOW) == 0 and calls == []


def test_flag_off_disables(env, monkeypatch):
    assert dj.judge_enabled()
    for v in ("false", "0", "no", "off"):
        monkeypatch.setenv("EVI_DEBT_JUDGE", v)
        assert not dj.judge_enabled()
    monkeypatch.delenv("EVI_DEBT_JUDGE")
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "false")
    assert not dj.judge_enabled()
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    monkeypatch.delenv("DATABASE_URL")
    assert not dj.judge_enabled()


def test_limit_respected_oldest_first(env, monkeypatch):
    jids = [f"55119000000{i}@s.whatsapp.net" for i in range(4)]
    for i, h in enumerate((10, 8, 6, 5)):
        env.add(jid=jids[i], in_id=f"m{i}", hours=h)
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, [])
    assert dj.judge_candidates(limit=2, now=NOW) == 2
    assert [env.rows[j]["judge_in_id"] for j in jids] == ["m0", "m1", None, None]


def test_prompt_wraps_third_party_and_marks_final(env, monkeypatch):
    env.add(preview="o contrato ficou assim")
    calls = []
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, calls)
    dj.judge_candidates(now=NOW)
    prompt = calls[0][1]
    final = prompt.split(dj.FINAL_MARK)[1]
    assert "«externo:whatsapp»" in final and "o contrato ficou assim" in final
    assert "Contato" in prompt and "[10:00] Usuário: oi" in prompt


def test_briefing_hook_survives_judge_failure(monkeypatch):
    from services import briefing

    monkeypatch.setattr(dj, "judge_enabled", lambda: True)

    def boom(limit=3, now=None):
        raise RuntimeError("down")

    monkeypatch.setattr(dj, "judge_candidates", boom)
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    monkeypatch.setattr(briefing.db, "list_pending_commitments", lambda limit=50: [])
    monkeypatch.setattr(rd, "list_debts", lambda *a, **k: [])
    assert briefing._collect_whatsapp() == []


def test_truncated_preview_never_ambiguous(env, monkeypatch):
    import db

    long = "o contrato ficou assim " * 10
    long = long[: db._PREVIEW_MAX]
    assert not rd.is_ambiguous(long)
    env.add(preview=long)
    calls = []
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, calls)
    assert dj.judge_candidates(now=NOW) == 0 and calls == []
    assert listed() == [JID]


@pytest.mark.parametrize("preview", ["[áudio]", "[mídia]", "[figurinha]"])
def test_media_placeholder_never_ambiguous(env, monkeypatch, preview):
    assert not rd.is_ambiguous(preview)
    env.add(preview=preview)
    calls = []
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, calls)
    assert dj.judge_candidates(now=NOW) == 0 and calls == []
    assert listed() == [JID]


def test_final_timestamp_is_local_time(env, monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    env.add(hours=6)  # 09:00 UTC -> 06:00 local
    calls = []
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, calls)
    dj.judge_candidates(now=NOW)
    assert "[06:00] Contato:" in calls[0][1]


def test_backoff_cooldown_and_max_attempts(env, monkeypatch):
    env.add()
    calls = []
    llm(monkeypatch, None, calls)
    assert dj.judge_candidates(now=NOW) == 0 and len(calls) == 1
    dj.judge_candidates(now=NOW)
    assert len(calls) == 1  # within cooldown: zero LLM calls
    for _ in range(3):
        k = (JID, "m1")
        dj._backoff[k] = (dj._backoff[k][0], dj._backoff[k][1] - dj.RETRY_COOLDOWN_SEC - 1)
        dj.judge_candidates(now=NOW)
    assert len(calls) == 3  # attempts exhausted: stops
    assert listed() == [JID]


def test_backoff_does_not_consume_limit(env, monkeypatch):
    env.add(jid="5511900000001@s.whatsapp.net", in_id="a", hours=10)
    env.add(jid="5511900000002@s.whatsapp.net", in_id="b", hours=8)
    dj._backoff[("5511900000001@s.whatsapp.net", "a")] = (1, dj.time.monotonic())
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, [])
    assert dj.judge_candidates(limit=1, now=NOW) == 1
    assert env.rows["5511900000002@s.whatsapp.net"]["judge_in_id"] == "b"


def test_verdict_written_with_original_jid(env, monkeypatch):
    lid = "123456@lid"
    env.add(jid=lid)
    from services import contact_identity

    monkeypatch.setattr(contact_identity, "canonical_jid", lambda j: JID if j == lid else j)
    monkeypatch.setattr(rd, "fold_alias_states", lambda: None)
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, [])
    assert dj.judge_candidates(now=NOW) == 1
    assert env.rows[lid]["judge_in_id"] == "m1"


def test_deadline_stops_further_candidates(env, monkeypatch):
    for i in range(3):
        env.add(jid=f"55119000000{i}@s.whatsapp.net", in_id=f"m{i}", hours=10 - i)
    calls = []
    llm(monkeypatch, {"needs_reply": False, "reason": "x"}, calls)
    assert dj.judge_candidates(limit=3, now=NOW, deadline_sec=-1) == 0
    assert calls == []
