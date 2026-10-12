"""SCN-DEBT-04 — promises captured from the user's own direct WhatsApp messages."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from services import promises  # noqa: E402
from services.message_sources import IncomingMessage  # noqa: E402
from services.session_memory import reset_for_tests  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "evolution"
DIRECT = "5511988887777@s.whatsapp.net"


@pytest.mark.parametrize(
    "text",
    [
        "te mando a proposta amanhã",
        "Te envio o contrato hoje à tarde",
        "te passo o telefone do eletricista",
        "Te aviso assim que chegar",
        "vejo e te falo",
        "Vejo isso e te falo amanhã",
        "te respondo mais tarde",
        "TE RETORNO na segunda",
        "amanhã te confirmo",
        "depois te explico direito",
        "vou ver e te digo",
        "deixa comigo, resolvo isso",
        "pode deixar que eu vejo",
    ],
)
def test_detect_promise_positive(text):
    assert promises.detect_promise(text)


@pytest.mark.parametrize(
    "text",
    ["Pode deixar", "Ahh ss, pode deixar", "Aí eu te aviso", "Pera q já te mando", "Ahh okk, pode deixar"],
)
def test_detect_promise_ignores_bare_acknowledgements(text):
    assert not promises.detect_promise(text)


@pytest.mark.parametrize(
    "text",
    [
        "você me manda o endereço?",
        "te mandei ontem o arquivo",
        "não te mando mais nada",
        "nunca te envio coisa assim",
        "te mando amanhã?",
        "ok, valeu",
        "",
        None,
        "quem te falou isso?",
    ],
)
def test_detect_promise_negative(text):
    assert not promises.detect_promise(text)


class FakeDb:
    def __init__(self):
        self.inbound, self.outbound, self.pending = [], [], []

    def init_db(self):
        pass

    def record_inbound(self, *a):
        self.inbound.append(a)

    def record_outbound(self, *a):
        self.outbound.append(a)

    def get_whatsapp_contact(self, jid):
        return {"jid": jid, "display_name": "Marina Costa", "whatsapp_label": "Mari"}

    def insert_pending_commitment(self, **kw):
        if any(p["source_id"] == kw["source_id"] for p in self.pending):
            return None
        self.pending.append(kw)
        return len(self.pending)


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeDb()
    monkeypatch.setitem(sys.modules, "db", fake)
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/fake")
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "")
    return fake


def _msg(text, jid=DIRECT, from_me=True, ts="2026-06-03T10:00:00+00:00", mid="m1"):
    return IncomingMessage(
        id=mid, sender=jid, text=text, ts=ts, from_me=from_me, is_group="@g.us" in jid
    )


def test_scn_debt_04_promise_with_tomorrow_date(fake_db):
    assert promises.capture_promises([_msg("te mando a proposta amanhã")]) == 1
    row = fake_db.pending[0]
    assert row["ctype"] == "promise" and row["source"] == "whatsapp_from_me"
    assert row["source_id"] == "m1" and row["source_chat"] == DIRECT
    assert row["source_label"] == "Marina Costa"
    assert row["due_date"] == "2026-06-04"
    assert row["raw_text"] == "te mando a proposta amanhã"
    assert row["status"] == "pending"


def test_promise_date_is_local_tomorrow_at_2230_sao_paulo(fake_db, monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    # 22:30 local on 06-03 == 01:30 UTC on 06-04
    promises.capture_promises([_msg("te mando a proposta amanhã", ts="2026-06-04T01:30:00Z")])
    assert fake_db.pending[0]["due_date"] == "2026-06-04"


def test_title_truncated_and_undated_promise(fake_db):
    promises.capture_promises([_msg("te aviso " + "x" * 200)])
    row = fake_db.pending[0]
    assert len(row["title"]) <= 80 and row["due_date"] is None


def test_idempotent(fake_db):
    m = _msg("te mando amanhã")
    promises.capture_promises([m])
    promises.capture_promises([m])
    assert len(fake_db.pending) == 1


def test_skips_inbound_group_control_and_no_match(fake_db, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "5511900000000@s.whatsapp.net")
    promises.capture_promises(
        [
            _msg("te mando amanhã", from_me=False, mid="a"),
            _msg("te mando amanhã", jid="1203630@g.us", mid="b"),
            _msg("te mando amanhã", jid="5511900000000@s.whatsapp.net", mid="c"),
            _msg("bom dia", mid="d"),
        ]
    )
    assert fake_db.pending == []


def test_no_database_url_is_noop(fake_db, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    assert promises.capture_promises([_msg("te mando amanhã")]) == 0
    assert fake_db.pending == []


def test_db_failure_soft_fails(fake_db):
    fake_db.insert_pending_commitment = MagicMock(side_effect=RuntimeError("boom"))
    assert promises.capture_promises([_msg("te mando amanhã")]) == 0


# --- webhook ---------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path, fake_db):
    monkeypatch.setenv("EVI_API_KEY", "")
    monkeypatch.setenv("EVI_LOG_DIR", str(tmp_path))
    main.app_state.graph = MagicMock()
    reset_for_tests()
    return TestClient(main.app)


def _post(client, text):
    payload = json.loads((FIXTURES / "messages_upsert_from_me.json").read_text())
    payload["data"]["messages"][0]["message"]["conversation"] = text
    with patch("services.contact_filesystem.ingest_commitment"), patch(
        "services.graph_sync.sync_commitment"
    ), patch("services.message_timeline.record_whatsapp_messages"):
        return client.post("/webhooks/evolution", json=payload)


def test_webhook_flag_on_stores_promise(client, fake_db, monkeypatch):
    monkeypatch.setenv("EVI_REPLY_DEBTS_ENABLED", "true")
    assert _post(client, "te mando a proposta amanhã").status_code == 200
    assert len(fake_db.pending) == 1
    row = fake_db.pending[0]
    assert row["ctype"] == "promise" and row["source_chat"] == DIRECT
    assert row["due_date"] is not None


def test_webhook_flag_off_stores_nothing(client, fake_db, monkeypatch):
    monkeypatch.delenv("EVI_REPLY_DEBTS_ENABLED", raising=False)
    assert _post(client, "te mando a proposta amanhã").status_code == 200
    assert fake_db.pending == []
