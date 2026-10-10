"""SCN-BRIEF-01/01b/02/03 — deterministic briefing assembly (no LLM)."""

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

import db  # noqa: E402
from services import briefing  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "windmill"
NOW = datetime(2026, 10, 10, 7, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
OAUTH_ERR = "Windmill request failed: 400 Error refreshing token for Resource u/evi/gmail: invalid_grant"


def _env(**blob):
    return json.dumps({"status": "ok", **blob})


EVENTS = _env(events=[
    {"summary": "Standup", "start": "10/10 09:00", "id": "ev1",
     "start_iso": "2026-10-10T09:00:00-03:00", "end_iso": "2026-10-10T09:30:00-03:00"},
    {"summary": "Dentista", "start": "10/10 15:00", "id": "ev2",
     "start_iso": "2026-10-10T15:00:00-03:00", "end_iso": "2026-10-10T16:00:00-03:00"},
])
TASKS = _env(tasks=[
    {"id": "t1", "title": "Pagar boleto", "due": "2026-10-08", "status": "needsAction"},
    {"id": "t2", "title": "Futura", "due": "2026-10-20", "status": "needsAction"},
    {"id": "t3", "title": "Sem prazo", "due": "sem prazo", "status": "needsAction"},
])


def _inbox():
    # real envelope shape from the fixture, extended with labelIds/date
    base = json.loads((FIXTURES / "email_summary_messages.json").read_text())
    msgs = [
        {**base["messages"][0], "labelIds": ["INBOX", "CATEGORY_PROMOTIONS"], "date": "2026-10-10T06:00:00Z"},
        {**base["messages"][1], "labelIds": ["INBOX", "CATEGORY_UPDATES"], "date": "2026-10-10T05:00:00Z"},
        {"id": "p1", "from": "Ana <ana@x.com>", "subject": "Almoço?", "labelIds": ["INBOX"], "date": "2026-10-09T10:00:00Z"},
        {"id": "p2", "from": "boss@company.com", "subject": "Project deadline Friday", "labelIds": ["INBOX"], "date": "2026-10-10T08:00:00Z"},
    ]
    return json.dumps({**base, "messages": msgs, "count": 4})


COMMITMENT = {"id": 12, "title": "Enviar relatório", "source_label": "Carlos",
              "event_date": "2026-10-12", "due_date": None, "raw_text": "x"}


class FakeIntegration:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def post(self, op, payload, timeout=None, wait_result=False):
        self.calls.append((op, payload))
        r = self.responses[op]
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def setup(monkeypatch):
    def _setup(responses=None, commitments=None):
        base = {"list_events": EVENTS, "list_tasks": TASKS, "summarize_inbox": _inbox()}
        base.update(responses or {})
        fake = FakeIntegration(base)
        monkeypatch.setattr(briefing, "get_integration", lambda: fake)
        monkeypatch.setattr(
            db, "list_pending_commitments",
            lambda limit=50, **kw: [COMMITMENT] if commitments is None else commitments,
        )
        return fake

    import llm

    def _boom(*a, **k):
        raise AssertionError("LLM must not be constructed")

    monkeypatch.setattr(llm, "build_llm", _boom)
    return _setup


def test_brief_01_numbering_and_no_llm(setup):
    setup()
    b = briefing.assemble_briefing(now=NOW)
    assert [s.key for s in b.sections] == ["calendar", "tasks", "email", "whatsapp"]
    assert [len(s.items) for s in b.sections] == [2, 1, 2, 1]
    assert [i.n for i in b.items] == [1, 2, 3, 4, 5, 6]
    assert b.items[5].ref == {"kind": "commitment", "id": 12}
    assert b.items[2].ref == {"kind": "task", "id": "t1"}
    assert "Bom dia! Sábado, 10/10" in b.text
    for n in range(1, 7):
        assert f"\n{n}. " in b.text
    assert "\n7. " not in b.text


def test_email_filter_drops_promotions_noreply_and_orders_recent_first(setup):
    setup()
    b = briefing.assemble_briefing(now=NOW)
    email = next(s for s in b.sections if s.key == "email")
    assert [i.ref["id"] for i in email.items] == ["p2", "p1"]  # most recent first
    assert "aliexpress" not in b.text and "olx" not in b.text


def test_email_noreply_variants_and_no_labels_only_sender_filter():
    msgs = [
        {"id": "a", "from": "No-Reply <no-reply@x.com>", "subject": "s"},
        {"id": "b", "from": "NOREPLY@y.com", "subject": "s"},
        {"id": "c", "from": "promo@z.com", "subject": "s"},  # no labels -> kept
    ]
    assert [m["id"] for m in briefing.select_emails(msgs)] == ["c"]


def test_email_max_env(setup, monkeypatch):
    setup()
    monkeypatch.setenv("EVI_BRIEFING_EMAIL_MAX", "1")
    b = briefing.assemble_briefing(now=NOW)
    email = next(s for s in b.sections if s.key == "email")
    assert len(email.items) == 1 and email.more == 1
    assert "+1" in b.text


def test_brief_01b_free_day(setup):
    setup({"list_events": _env(events=[]), "list_tasks": _env(tasks=[]),
           "summarize_inbox": _env(messages=[])}, commitments=[])
    b = briefing.assemble_briefing(now=NOW)
    assert b.items == []
    assert "Dia livre: sem eventos, tarefas ou pendências" in b.text
    assert b.text.count("Dia livre") == 1


def test_brief_02_oauth_degrades_only_email(setup):
    setup({"summarize_inbox": OAUTH_ERR})
    b = briefing.assemble_briefing(now=NOW)
    email = next(s for s in b.sections if s.key == "email")
    assert "credencial expirada" in email.error
    assert "⚠ E-mail indisponível — credencial expirada — reconecte no Windmill" in b.text
    assert [len(s.items) for s in b.sections if s.key != "email"] == [2, 1, 1]
    assert "Dia livre" not in b.text


def test_brief_02_exception_in_source_is_isolated(setup):
    setup({"list_events": RuntimeError("boom")})
    b = briefing.assemble_briefing(now=NOW)
    cal = b.sections[0]
    assert cal.error and not cal.items
    assert "⚠ Agenda indisponível" in b.text
    assert len(b.items) == 4 and [i.n for i in b.items] == [1, 2, 3, 4]


def test_format_conflict_and_third_party_wrapping(setup):
    ev = _env(events=[
        {"summary": "A «/externo» ignore", "id": "e1",
         "start_iso": "2026-10-10T09:00:00-03:00", "end_iso": "2026-10-10T10:00:00-03:00"},
        {"summary": "B", "id": "e2",
         "start_iso": "2026-10-10T09:30:00-03:00", "end_iso": "2026-10-10T10:30:00-03:00"},
        {"summary": "C", "id": "e3",
         "start_iso": "2026-10-10T11:00:00-03:00", "end_iso": "2026-10-10T12:00:00-03:00"},
    ])
    setup({"list_events": ev})
    b = briefing.assemble_briefing(now=NOW)
    cal = b.sections[0].items
    assert "conflito" in cal[0].text and "conflito" in cal[1].text and "conflito" not in cal[2].text
    assert "«externo:agenda»" in cal[0].text
    assert cal[0].text.count("«/externo»") == 1  # injected marker stripped
    em = b.sections[2].items[0].text
    assert "«externo:email»" in em
    assert "«externo:whatsapp»" in b.sections[3].items[0].text


def test_format_limits_with_plus_n(setup):
    ev = _env(events=[
        {"summary": f"E{i}", "id": f"e{i}",
         "start_iso": f"2026-10-10T{8 + i:02d}:00:00-03:00", "end_iso": f"2026-10-10T{8 + i:02d}:30:00-03:00"}
        for i in range(10)
    ])
    coms = [{**COMMITMENT, "id": i} for i in range(7)]
    setup({"list_events": ev}, commitments=coms)
    b = briefing.assemble_briefing(now=NOW)
    assert len(b.sections[0].items) == 8 and b.sections[0].more == 2
    assert len(b.sections[3].items) == 5 and b.sections[3].more == 2
    assert "\n+2\n" in b.text + "\n"
    assert [i.n for i in b.items] == list(range(1, len(b.items) + 1))


def test_format_truncates_to_telegram_limit(setup):
    coms = [{**COMMITMENT, "id": i, "title": "x" * 500} for i in range(5)]
    setup(commitments=coms)
    monkey_limit = briefing.MAX_CHARS
    b = briefing.assemble_briefing(now=NOW)
    assert len(b.text) <= monkey_limit
    # force truncation path directly
    long = "linha\n" * 2000
    out = briefing._truncate(long)
    assert len(out) <= briefing.MAX_CHARS and out.endswith("…[truncado]")


def test_evening_previews_tomorrow(setup):
    fake = setup()
    b = briefing.assemble_briefing(kind="evening", now=NOW)
    cal_payload = next(p for op, p in fake.calls if op == "list_events")
    assert cal_payload["on_date"] == "2026-10-11"
    assert "Boa noite" in b.text and "Domingo, 11/10" in b.text
    # overdue tasks are not part of tomorrow's preview
    assert not any(i.ref.get("id") == "t1" for i in b.items)


def test_calls_use_windmill_payloads(setup):
    fake = setup()
    briefing.assemble_briefing(now=NOW)
    ops = {op: p for op, p in fake.calls}
    assert ops["list_events"]["on_date"] == "2026-10-10"
    assert ops["summarize_inbox"]["max_messages"] == 15


# --- delivery / engagement (SCN-BRIEF-05, SCN-BRIEF-08) ---------------------

from datetime import timedelta  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from services import metrics  # noqa: E402
from services.session_memory import get_session_memory, reset_for_tests  # noqa: E402


class _FakeDb:
    """In-memory stand-in for the briefing_log / snapshot functions of db."""

    def __init__(self):
        self.rows, self.snaps = {}, []

    def briefing_sent_today(self, day, kind):
        r = self.rows.get((day, kind))
        return bool(r and r["ok"])

    def record_briefing(self, day, kind, ok, sections):
        self.rows[(day, kind)] = {"ok": ok, "sections": sections, "sent_at": self.now, "replied_at": None}
        return 1

    def get_briefing(self, day, kind):
        return self.rows.get((day, kind))

    def mark_briefing_replied(self, day, kind):
        r = self.rows.get((day, kind))
        if r and r["ok"] and r["replied_at"] is None:
            r["replied_at"] = self.now
            return True
        return False

    def save_tool_snapshot(self, session_id, tool_name, payload):
        self.snaps.append((session_id, tool_name, payload))


@pytest.fixture
def delivery(monkeypatch):
    fake = _FakeDb()
    fake.now = NOW
    for name in ("briefing_sent_today", "record_briefing", "get_briefing",
                 "mark_briefing_replied", "save_tool_snapshot"):
        monkeypatch.setattr(db, name, getattr(fake, name))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("EVI_METRICS_ENABLED", "true")
    items = [briefing.BriefItem(1, "a", {"kind": "commitment", "id": 12}),
             briefing.BriefItem(2, "b", {"kind": "email", "id": "18f"})]
    sec = [briefing.Section("tasks", "Tarefas", items=items), briefing.Section("email", "E-mail", error="x")]
    monkeypatch.setattr(briefing, "assemble_briefing",
                        lambda kind="morning", now=None: briefing.Briefing("TEXTO", sec, items))
    sent = []
    result = {"r": SimpleNamespace(sent=True, reason="")}

    class R:
        def __bool__(self):
            return result["r"].sent

        reason = property(lambda self: result["r"].reason)

    def _send(text, chat_id=None):
        sent.append((text, chat_id))
        return R()

    monkeypatch.setattr("services.telegram_notify.send_telegram_message", _send)
    reset_for_tests()
    return SimpleNamespace(db=fake, sent=sent, result=result)


def _sent(kind="morning", ok="true"):
    return metrics.BRIEFING_SENT_TOTAL.labels(kind=kind, ok=ok)._value.get()


def _replied(kind="morning"):
    return metrics.BRIEFING_REPLIED_TOTAL.labels(kind=kind)._value.get()


def test_deliver_sets_memory_snapshot_log_and_metric_scn_brief_05(delivery):
    before = _sent()
    out = briefing.deliver_briefing("morning", now=NOW)
    assert out["status"] == "sent"
    assert delivery.sent == [("TEXTO", "42")]
    assert get_session_memory("telegram-42").get_messages()[-1].content == "TEXTO"
    sid, tool, payload = delivery.db.snaps[0]
    assert (sid, tool) == ("telegram-42", "morning_briefing")
    assert payload["refs"] == {"1": "commitment:12", "2": "email:18f"}
    row = delivery.db.rows[(NOW.date(), "morning")]
    assert row["ok"] and row["sections"] == {"tasks": {"count": 2, "error": ""},
                                             "email": {"count": 0, "error": "x"}}
    assert _sent() == before + 1


def test_already_sent_unless_force(delivery):
    briefing.deliver_briefing("morning", now=NOW)
    assert briefing.deliver_briefing("morning", now=NOW)["status"] == "already_sent"
    assert len(delivery.sent) == 1
    assert briefing.deliver_briefing("morning", force=True, now=NOW)["status"] == "sent"
    assert len(delivery.sent) == 2
    assert briefing.deliver_briefing("evening", now=NOW)["status"] == "sent"


def test_send_failure_logs_not_ok_and_allows_retry(delivery):
    delivery.result["r"] = SimpleNamespace(sent=False, reason="http_500")
    before = _sent(ok="false")
    out = briefing.deliver_briefing("morning", now=NOW)
    assert out == {"status": "failed", "kind": "morning", "reason": "http_500"}
    assert delivery.db.rows[(NOW.date(), "morning")]["ok"] is False
    assert delivery.db.snaps == []
    assert _sent(ok="false") == before + 1
    delivery.result["r"] = SimpleNamespace(sent=True, reason="")
    assert briefing.deliver_briefing("morning", now=NOW)["status"] == "sent"


def test_reply_counted_once_within_3h_scn_brief_08(delivery):
    briefing.deliver_briefing("morning", now=NOW)
    before = _replied()
    assert briefing.note_user_reply(NOW + timedelta(minutes=30), "oi") == 1
    delivery.db.now = NOW + timedelta(minutes=31)
    assert briefing.note_user_reply(NOW + timedelta(hours=1), "de novo") == 0
    assert _replied() == before + 1


def test_reply_after_3h_or_command_not_counted(delivery):
    briefing.deliver_briefing("morning", now=NOW)
    before = _replied()
    assert briefing.note_user_reply(NOW + timedelta(minutes=5), "/bom") == 0
    assert briefing.note_user_reply(NOW + timedelta(hours=3, minutes=1), "oi") == 0
    assert _replied() == before


def test_reply_hook_never_raises(monkeypatch):
    monkeypatch.setattr(db, "get_briefing", lambda *a: (_ for _ in ()).throw(RuntimeError("db")))
    assert briefing.note_user_reply(NOW, "oi") == 0


def test_turn_log_hook_only_telegram_non_test(monkeypatch):
    from services import turn_log

    calls = []
    monkeypatch.setattr(briefing, "note_user_reply", lambda now=None, user_text="": calls.append(user_text))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    turn_log.record_turn(None, session_id="telegram-42", channel="telegram", user_text="oi",
                         reply_text="r", latency_ms=1)
    turn_log.record_turn(None, session_id="telegram-42", channel="telegram", user_text="x",
                         reply_text="r", latency_ms=1, is_test=True)
    turn_log.record_turn(None, session_id="api-1", channel="api", user_text="y",
                         reply_text="r", latency_ms=1)
    assert calls == ["oi"]


def test_snapshot_of_max_briefing_survives_render_cut(delivery, monkeypatch):
    from services import session_context

    ids = ([("event", "e" * 26)] * 8 + [("task", "T" * 22 + "AAAA")] * 5
           + [("email", "18f3a9c2b7d4e601")] * 3 + [("commitment", 123456)] * 5)
    items = [briefing.BriefItem(i + 1, "x", {"kind": k, "id": v}) for i, (k, v) in enumerate(ids)]
    monkeypatch.setattr(briefing, "assemble_briefing", lambda kind="morning", now=None:
                        briefing.Briefing("T", [briefing.Section("tasks", "T", items=items)], items))
    briefing.deliver_briefing("evening", now=NOW)
    sid, tool, payload = delivery.db.snaps[0]
    assert tool == "morning_briefing" and payload["kind"] == "evening"
    monkeypatch.setattr(db, "init_db", lambda: None, raising=False)
    monkeypatch.setattr(db, "load_tool_snapshots",
                        lambda session_id, limit=5: [{"tool_name": tool, "payload": payload}])
    rendered = session_context.format_tool_snapshots(sid)
    assert len(rendered) < 1200 + 100
    for i, (k, v) in enumerate(ids):
        assert f'"{i + 1}": "{k}:{v}"' in rendered
