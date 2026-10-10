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
