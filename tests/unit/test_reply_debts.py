"""SCN-DEBT-02 — per-conversation WhatsApp state recorded by the webhook."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from services import reply_debts  # noqa: E402
from services.message_sources import IncomingMessage  # noqa: E402
from services.session_memory import reset_for_tests  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "evolution"
DIRECT = "5511988887777@s.whatsapp.net"


class FakeDb:
    def __init__(self):
        self.inbound, self.outbound = [], []
        self.pending = []

    def init_db(self):
        pass

    def record_inbound(self, jid, ts, preview, msg_id):
        self.inbound.append((jid, ts, preview, msg_id))

    def record_outbound(self, jid, ts):
        self.outbound.append((jid, ts))

    def insert_pending_commitment(self, *a, **k):
        self.pending.append((a, k))
        return 1


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeDb()
    monkeypatch.setitem(sys.modules, "db", fake)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/fake")
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "")
    return fake


def _msg(jid=DIRECT, text="oi", from_me=False, ts="2026-06-03T10:00:00+00:00", mid="m1"):
    return IncomingMessage(
        id=mid, sender=jid, text=text, ts=ts, from_me=from_me,
        is_group="@g.us" in jid,
    )


def test_inbound_direct_records_preview_and_id(fake_db):
    assert reply_debts.track_conversation([_msg(text="x" * 300)]) == 1
    jid, ts, preview, mid = fake_db.inbound[0]
    assert jid == DIRECT and mid == "m1" and ts.year == 2026
    assert fake_db.outbound == []


def test_from_me_records_outbound_only(fake_db):
    reply_debts.track_conversation([_msg(from_me=True)])
    assert fake_db.outbound[0][0] == DIRECT
    assert fake_db.inbound == []


def _timeline(tmp_path, jid=DIRECT):
    from services.contact_filesystem import read_timeline_tail

    return read_timeline_tail(jid, limit=10)


def test_scn_mem_14_from_me_direct_goes_to_timeline_once(fake_db, monkeypatch, tmp_path):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    m = _msg(from_me=True, text="te mando a modelagem quando terminar", mid="me1")
    reply_debts.track_conversation([m])
    reply_debts.track_conversation([m])  # duplicate id recorded once
    rows = _timeline(tmp_path)
    assert [r["text_preview"] for r in rows] == ["[eu] te mando a modelagem quando terminar"]
    assert fake_db.pending == [], "no commitment extracted from fromMe"


def test_from_me_echo_group_and_newsletter_not_in_timeline(fake_db, monkeypatch, tmp_path):
    monkeypatch.setenv("EVI_CONTACT_MEMORY_DIR", str(tmp_path))
    reply_debts.track_conversation([
        _msg(from_me=True, text="[EVI] já respondi", mid="e1"),
        _msg(jid="1203630@g.us", from_me=True, mid="g1"),
        _msg(jid="120363@newsletter", from_me=True, mid="n1"),
    ])
    assert not (tmp_path / "contacts").exists() or not list((tmp_path / "contacts").iterdir())


def test_group_control_and_echo_are_skipped(fake_db, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "5511777@s.whatsapp.net")
    n = reply_debts.track_conversation([
        _msg(jid="1203630@g.us"),
        _msg(jid="5511777@s.whatsapp.net"),
        _msg(from_me=True, text="[EVI] já respondi"),
    ])
    assert n == 0 and not fake_db.inbound and not fake_db.outbound


def test_missing_timestamp_falls_back_to_now(fake_db):
    reply_debts.track_conversation([_msg(ts="")])
    assert fake_db.inbound[0][1].tzinfo is not None


def test_no_database_url_is_a_noop(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert reply_debts.track_conversation([_msg()]) == 0


def test_db_failure_never_raises(fake_db):
    def boom(*a, **k):
        raise RuntimeError("db down")

    fake_db.record_inbound = boom
    assert reply_debts.track_conversation([_msg()]) == 0


# --- webhook ---------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path, fake_db):
    monkeypatch.setenv("EVI_API_KEY", "")
    monkeypatch.setenv("EVI_LOG_DIR", str(tmp_path))
    main.app_state.graph = MagicMock()
    reset_for_tests()
    return TestClient(main.app)


def _post(client, payload):
    with patch("services.contact_filesystem.ingest_commitment"), patch(
        "services.graph_sync.sync_commitment"
    ), patch("services.message_timeline.record_whatsapp_messages"):
        return client.post("/webhooks/evolution", json=payload)


def test_scn_debt_02_from_me_updates_last_out_without_commitment(client, fake_db):
    payload = json.loads((FIXTURES / "messages_upsert_from_me.json").read_text())
    r = _post(client, payload)
    assert r.status_code == 200
    assert [o[0] for o in fake_db.outbound] == [DIRECT]
    assert fake_db.inbound == []
    assert fake_db.pending == [], "fromMe never reaches extraction"
    assert r.json()["ingested"] == 0


def test_scn_debt_02_group_updates_no_state(client, fake_db):
    payload = json.loads((FIXTURES / "messages_upsert_from_me.json").read_text())
    payload["data"]["messages"][0]["key"]["remoteJid"] = "1203630@g.us"
    _post(client, payload)
    assert not fake_db.outbound and not fake_db.inbound


def test_control_chat_updates_no_state(client, fake_db, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", DIRECT)
    payload = json.loads((FIXTURES / "messages_upsert_from_me.json").read_text())
    with patch(
        "services.whatsapp_control.process_whatsapp_control_message",
        return_value={"ok": True},
    ):
        _post(client, payload)
    assert not fake_db.outbound and not fake_db.inbound


def test_inbound_webhook_records_inbound(client, fake_db):
    payload = json.loads((FIXTURES / "messages_upsert.json").read_text())
    _post(client, payload)
    assert fake_db.inbound and fake_db.inbound[0][3] == "evo001"


def test_tracking_failure_does_not_break_webhook(client, fake_db):
    with patch("services.reply_debts.track_conversation", side_effect=RuntimeError("x")):
        payload = json.loads((FIXTURES / "messages_upsert.json").read_text())
        assert _post(client, payload).status_code == 200


# --- debt query + closing filter (SCN-DEBT-01, SCN-DEBT-03) -------------------


@pytest.mark.parametrize(
    "text",
    ["ok", "OK!", "okay", "blz", "beleza", "valeu", "vlw", "obrigado", "Obrigada!",
     "brigado", "muito obrigado", "valeu 👍", "👍", "👍🙏", "de nada", "tmj", "show",
     "top", "ok, valeu.", "Ok. Obrigado!!", "...",
     # closings v2 (SCN-UX-05)
     "Joia", "jóia", "JOIA!", "Tranquilo", "tranquilo 🙏", "Fechou, valeu!", "fechou",
     "ótimo", "Perfeito!", "combinado", "👍🏽", "👌", "😊", "❤️", "🙏🏾",
     "obrigado, Marcão!", "valeu Ana", "brigadão fulano", "muito obrigada, Dani 😊",
     "Obrigada Dani!!", "VLW, Zé", "obrigado, Marcão 👍"],
)
def test_closing_positive(text):
    assert reply_debts.is_closing_message(text)


@pytest.mark.parametrize(
    "text",
    ["ok, me manda amanhã?", "consegue me mandar o orçamento?", "valeu, e o prazo?",
     "obrigado, mas ainda preciso do contrato", "", None, "okupa", "123",
     "valeu, me manda o contrato?", "valeu! me manda o contrato", "obrigado, Marcão, consegue ver isso?",
     "joia, qual o valor", "fechou, quando começa", "perfeito, pode me passar o link",
     "obrigado pelo contrato", "valeu Ana, como faço?", "tranquilo?", "obrigado pelo envio, Ana"],
)
def test_closing_negative(text):
    assert not reply_debts.is_closing_message(text)


def test_list_debts_filters_closing_and_formats(monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 6, 3, 18, 0, tzinfo=timezone.utc)
    rows = [
        {"jid": "a@s.whatsapp.net", "last_in_at": now - timedelta(hours=9),
         "last_in_preview": "valeu 👍"},
        {"jid": "b@s.whatsapp.net", "last_in_at": now - timedelta(hours=6),
         "last_in_preview": "consegue me mandar o orçamento?"},
    ]
    seen = {}

    class Db:
        def init_db(self):
            pass

        def list_debt_candidates(self, n, mn, mx, limit=200):
            seen.update(now=n, mn=mn, mx=mx)
            return rows

        def get_whatsapp_contact(self, jid):
            return {"display_name": "Fulana"} if jid.startswith("b") else None

    monkeypatch.setitem(sys.modules, "db", Db())
    monkeypatch.delenv("EVI_REPLY_DEBT_HOURS", raising=False)
    out = reply_debts.list_debts(now=now)
    assert [d["name"] for d in out] == ["Fulana"]
    assert out[0]["preview"].startswith("consegue") and round(out[0]["age_h"]) == 6
    assert seen["mn"] == timedelta(hours=4) and seen["mx"] == timedelta(days=7)


def test_list_debts_v2_closings_dropped_but_closing_plus_request_kept(monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
    previews = {"a": "Joia", "b": "obrigado, Marcão!", "c": "Tranquilo",
                "d": "Fechou, valeu!", "e": "valeu, me manda o contrato?"}
    rows = [{"jid": f"{k}@s.whatsapp.net", "last_in_at": now - timedelta(hours=6),
             "last_in_preview": v} for k, v in previews.items()]

    class Db:
        def init_db(self):
            pass

        def list_debt_candidates(self, n, mn, mx, limit=200):
            return rows

        def get_whatsapp_contact(self, jid):
            return None

    monkeypatch.setitem(sys.modules, "db", Db())
    out = reply_debts.list_debts(now=now)
    assert [d["jid"] for d in out] == ["e@s.whatsapp.net"]


def test_tools_empty_and_listing(monkeypatch):
    from tools import reply_debt_tools

    monkeypatch.setattr("services.reply_debts.list_debts", lambda **k: [])
    assert reply_debt_tools.list_reply_debts.invoke({}) == "Ninguém esperando sua resposta."
    monkeypatch.setattr(
        "services.reply_debts.list_debts",
        lambda **k: [{"jid": "b@s.whatsapp.net", "name": "Fulana", "since": None,
                      "age_h": 6.2, "preview": "manda o orçamento?"}],
    )
    out = reply_debt_tools.list_reply_debts.invoke({})
    assert out.startswith("Fulana — há 6 h: «externo:whatsapp»") and "«/externo»" in out


def test_dismiss_tool_resolves_name_and_acknowledges(monkeypatch):
    from tools import reply_debt_tools

    acked = []

    class Db:
        def init_db(self):
            pass

        def acknowledge(self, jid, ts):
            acked.append(jid)

    monkeypatch.setitem(sys.modules, "db", Db())
    monkeypatch.setattr(
        "services.contact_filesystem.resolve_contact_for_query",
        lambda q: (("b@s.whatsapp.net", "Fulana"), "") if q == "Fulana" else (None, "nada"),
    )
    assert "Fulana" in reply_debt_tools.dismiss_reply_debt.invoke({"jid_or_name": "Fulana"})
    assert acked == ["b@s.whatsapp.net"]
    assert reply_debt_tools.dismiss_reply_debt.invoke({"jid_or_name": "zzz"}) == "nada"
    reply_debt_tools.dismiss_reply_debt.invoke({"jid_or_name": "c@s.whatsapp.net"})
    assert acked[-1] == "c@s.whatsapp.net"


def test_dismiss_tool_resolves_briefing_items(monkeypatch):
    from tools import reply_debt_tools

    acked = []

    class Db:
        def init_db(self):
            pass

        def acknowledge(self, jid, ts):
            acked.append(jid)

    monkeypatch.setitem(sys.modules, "db", Db())
    monkeypatch.setattr(
        "services.briefing.resolve_briefing_items",
        lambda nums, session_id=None, kind="commitment": (["a@s.whatsapp.net"], ["item 9 não existe"])
        if kind == "reply_debt" else ([], []),
    )
    out = reply_debt_tools.dismiss_reply_debt.invoke({"briefing_items": [1, 9]})
    assert acked == ["a@s.whatsapp.net"] and "item 9" in out


def test_one_way_jids_are_not_debts(monkeypatch):
    from services import reply_debts

    assert reply_debts.is_one_way_jid("120363173003902460@newsletter")
    assert reply_debts.is_one_way_jid("status@broadcast")
    assert not reply_debts.is_one_way_jid("5511988887777@s.whatsapp.net")


def test_scn_ux_01_ack_names_the_person_not_a_count_or_jid(monkeypatch):
    from services import reply_debts
    from tools import reply_debt_tools

    class Db:
        def init_db(self):
            pass

        def acknowledge(self, jid, ts):
            pass

    monkeypatch.setitem(sys.modules, "db", Db())
    monkeypatch.setattr(
        reply_debts, "list_debts",
        lambda: [{"jid": "a@s.whatsapp.net", "name": "Marina Teste"}, {"jid": "9@lid", "name": ""}],
    )
    monkeypatch.setattr(
        "services.briefing.resolve_briefing_items",
        lambda nums, session_id=None, kind="commitment": (["a@s.whatsapp.net"], []),
    )
    out = reply_debt_tools.dismiss_reply_debt.invoke({"briefing_items": [1]})
    assert out == "Ok, Marina Teste não aparece mais como pendente de resposta."
    monkeypatch.setattr(
        "services.briefing.resolve_briefing_items",
        lambda nums, session_id=None, kind="commitment": (["a@s.whatsapp.net", "9@lid"], []),
    )
    out = reply_debt_tools.dismiss_reply_debt.invoke({"briefing_items": [1, 2]})
    assert "Marina Teste e contato sem nome" in out and "@lid" not in out


def test_scn_ux_01_missing_item_error_states_the_valid_range(monkeypatch):
    from services import briefing

    monkeypatch.setattr(briefing.db, "load_tool_snapshots", lambda sid, limit=50: [
        {"tool_name": "morning_briefing", "created_at": "2026-10-13T08:00:00",
         "payload": {"day": briefing.now_local().date().isoformat(),
                     "refs": {"1": "reply_debt:a@s.whatsapp.net", "2": "reply_debt:b@s.whatsapp.net"}}}])
    ids, errors = briefing.resolve_briefing_items([9], session_id="s", kind="reply_debt")
    assert ids == [] and errors == ["item 9 não existe no briefing (o briefing vai de 1 a 2)"]


# --- closings v3 + acknowledgement rule (SCN-PREC-01, SCN-PREC-02) -----------


@pytest.mark.parametrize(
    "text",
    ["Boa", "boa!", "bom", "massa", "legal", "bacana", "dahora", "demorou", "falou",
     "isso", "uhum", "aham", "sim", "pode crer", "haha", "hahaha", "hehe", "kkk",
     "kkkkk", "rs", "rsrs", "Boa, valeu", "kkk 👍"],
)
def test_closing_v3_positive(text):
    assert reply_debts.is_closing_message(text)


@pytest.mark.parametrize(
    "text",
    ["boa tarde", "boa, me manda o contrato?", "sim, me manda", "isso funciona?",
     "coloca o bau na frente das cases"],
)
def test_closing_v3_negative(text):
    assert not reply_debts.is_closing_message(text)


def _debts(monkeypatch, rows, now):
    class Db:
        def init_db(self):
            pass

        def list_debt_candidates(self, n, mn, mx, limit=200):
            return rows

        def get_whatsapp_contact(self, jid):
            return None

    monkeypatch.setitem(sys.modules, "db", Db())
    return reply_debts.list_debts(now=now)


def test_scn_prec_01_ack_within_10min_not_listed(monkeypatch):
    from datetime import datetime, timedelta, timezone

    out_at = datetime(2026, 10, 12, 22, 13, 10, tzinfo=timezone.utc)
    now = out_at + timedelta(hours=6)
    rows = [
        {"jid": "a@s.whatsapp.net", "last_in_at": out_at + timedelta(seconds=22),
         "last_in_preview": "Boa", "last_out_at": out_at},
        {"jid": "b@s.whatsapp.net", "last_in_at": out_at + timedelta(minutes=2),
         "last_in_preview": "vou ver", "last_out_at": out_at},
    ]
    assert _debts(monkeypatch, rows, now) == []


def test_scn_prec_02_closing_word_hours_later_not_listed(monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
    out_at = now - timedelta(hours=9)
    rows = [{"jid": "a@s.whatsapp.net", "last_in_at": out_at + timedelta(hours=3),
             "last_in_preview": "boa", "last_out_at": out_at}]
    assert _debts(monkeypatch, rows, now) == []


def test_ack_rule_keeps_real_debts(monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
    out_at = now - timedelta(hours=12)
    near = out_at + timedelta(minutes=1)
    late = out_at + timedelta(hours=3)
    rows = [
        {"jid": "a@s.whatsapp.net", "last_in_at": near,
         "last_in_preview": "coloca o bau na frente das cases", "last_out_at": out_at},
        {"jid": "b@s.whatsapp.net", "last_in_at": near,
         "last_in_preview": "e aí?", "last_out_at": out_at},
        {"jid": "c@s.whatsapp.net", "last_in_at": late,
         "last_in_preview": "boa tarde", "last_out_at": out_at},
        {"jid": "d@s.whatsapp.net", "last_in_at": late,
         "last_in_preview": "vou ver", "last_out_at": out_at},
        {"jid": "e@s.whatsapp.net", "last_in_at": near,
         "last_in_preview": "boa, me manda o contrato?", "last_out_at": out_at},
    ]
    out = _debts(monkeypatch, rows, now)
    assert sorted(d["jid"][0] for d in out) == ["a", "b", "c", "d", "e"]


def test_is_acknowledgement_boundaries():
    from datetime import datetime, timedelta, timezone

    o = datetime(2026, 10, 12, 22, 0, tzinfo=timezone.utc)
    assert reply_debts.is_acknowledgement("vou ver", o + timedelta(minutes=10), o)
    assert not reply_debts.is_acknowledgement("vou ver", o + timedelta(minutes=11), o)
    assert not reply_debts.is_acknowledgement("vou ver", o + timedelta(minutes=1), None)
    assert not reply_debts.is_acknowledgement("vou ver", o - timedelta(minutes=1), o)
    assert not reply_debts.is_acknowledgement("vou ver isso agora", o + timedelta(minutes=1), o)
