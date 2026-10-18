"""SCN-AWAIT-01/02 — people who have not answered the user's question or request."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

import db  # noqa: E402
from services import awaiting_reply, contact_filesystem  # noqa: E402

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
BRUNO = "5511900000001@s.whatsapp.net"
CARLA = "5511900000002@s.whatsapp.net"


def _ago(days):
    return NOW - timedelta(days=days)


@pytest.fixture
def world(monkeypatch):
    """Fake conversation state + timelines + dismissals (no DB, no filesystem)."""
    w = type("W", (), {})()
    w.states, w.timeline, w.dismissed = [], {}, set()
    monkeypatch.delenv("EVI_AWAITING_DAYS", raising=False)
    monkeypatch.delenv("EVI_WHATSAPP_CONTROL_JIDS", raising=False)
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(db, "list_states", lambda: [])
    monkeypatch.setattr(db, "get_whatsapp_contact", lambda jid: {"whatsapp_label": w.labels.get(jid, "")})
    w.labels = {BRUNO: "Bruno", CARLA: "Carla"}

    def candidates(now, min_age, max_age, limit=200):
        rows = [
            s for s in w.states
            if s["last_out_at"] and s["last_out_at"] > (s.get("last_in_at") or datetime.min.replace(tzinfo=timezone.utc))
            and now - max_age <= s["last_out_at"] <= now - min_age
        ]
        return sorted(rows, key=lambda r: r["last_out_at"])[:limit]

    monkeypatch.setattr(db, "list_awaiting_candidates", candidates)
    monkeypatch.setattr(db, "is_awaiting_dismissed", lambda jid, out_at: (jid, out_at) in w.dismissed)
    monkeypatch.setattr("services.contact_identity.canonical_jid", lambda j: j)
    monkeypatch.setattr(
        contact_filesystem, "read_timeline_tail",
        lambda jid, limit=5: w.timeline.get(jid, [])[-limit:],
    )

    def add(jid, text, days, last_in_days=None, **entry):
        out_at = _ago(days)
        w.states.append({"jid": jid, "last_out_at": out_at,
                         "last_in_at": _ago(last_in_days) if last_in_days is not None else None})
        w.timeline.setdefault(jid, []).append(
            {"ts": out_at.isoformat(), "text_preview": f"[eu] {text}", **entry})
        return out_at

    w.add = add
    return w


def test_scn_await_01_question_four_days_ago_is_listed(world):
    out_at = world.add(BRUNO, "consegue me mandar o contrato?", 4)
    [c] = awaiting_reply.candidates(NOW)
    assert c["jid"] == BRUNO and c["label"] == "Bruno" and c["days"] == 4
    assert c["out_at"] == out_at and c["excerpt"] == "consegue me mandar o contrato?"


def test_scn_await_02_closing_message_is_not_listed(world):
    world.add(CARLA, "valeu, abraço!", 5)
    assert awaiting_reply.candidates(NOW) == []


def test_statement_without_question_or_request_is_not_listed(world):
    world.add(CARLA, "estou chegando às nove", 5)
    assert awaiting_reply.candidates(NOW) == []


def test_the_other_side_having_replied_excludes_the_conversation(world):
    world.add(BRUNO, "consegue me mandar o contrato?", 4, last_in_days=1)
    assert awaiting_reply.candidates(NOW) == []


def test_an_older_inbound_does_not_exclude_it(world):
    world.add(BRUNO, "consegue me mandar o contrato?", 4, last_in_days=6)
    assert [c["jid"] for c in awaiting_reply.candidates(NOW)] == [BRUNO]


def test_window_bounds_default_three_days_up_to_thirty(world, monkeypatch):
    for jid, days in (("a@s.whatsapp.net", 2), ("b@s.whatsapp.net", 3), ("c@s.whatsapp.net", 30),
                      ("d@s.whatsapp.net", 31)):
        world.add(jid, "pode me confirmar?", days)
    got = {c["jid"] for c in awaiting_reply.candidates(NOW, limit=10)}
    assert got == {"b@s.whatsapp.net", "c@s.whatsapp.net"}
    monkeypatch.setenv("EVI_AWAITING_DAYS", "5")
    assert {c["jid"] for c in awaiting_reply.candidates(NOW, limit=10)} == {"c@s.whatsapp.net"}


def test_oldest_first_and_limit(world):
    for i, days in enumerate((4, 9, 6, 12)):
        world.add(f"55119000001{i}@s.whatsapp.net", "pode me responder?", days)
    got = awaiting_reply.candidates(NOW, limit=3)
    assert [c["days"] for c in got] == [12, 9, 6]


def test_dismissal_is_per_outbound_message(world):
    out_at = world.add(BRUNO, "consegue me mandar o contrato?", 4)
    world.dismissed.add((BRUNO, out_at))
    assert awaiting_reply.candidates(NOW) == []
    world.states.clear()  # a newer message from the user reopens the conversation
    world.add(BRUNO, "e aí, conseguiu?", 3)
    assert [c["excerpt"] for c in awaiting_reply.candidates(NOW)] == ["e aí, conseguiu?"]


def test_groups_channels_and_control_chat_are_excluded(world, monkeypatch):
    monkeypatch.setenv("EVI_WHATSAPP_CONTROL_JIDS", "5511999999999@s.whatsapp.net")
    for jid in ("120363000000@g.us", "1203630@newsletter", "status@broadcast", "5511999999999@s.whatsapp.net"):
        world.add(jid, "alguém consegue me ajudar?", 5)
    assert awaiting_reply.candidates(NOW) == []


def test_no_timeline_text_or_stale_eu_entry_is_skipped(world):
    world.states.append({"jid": BRUNO, "last_out_at": _ago(4), "last_in_at": None})  # no timeline
    world.states.append({"jid": CARLA, "last_out_at": _ago(4), "last_in_at": None})
    world.timeline[CARLA] = [{"ts": _ago(20).isoformat(), "text_preview": "[eu] pode me ligar?"}]
    world.timeline[BRUNO] = [{"ts": _ago(4).isoformat(), "text_preview": "[Bruno] oi?"}]  # only theirs
    assert awaiting_reply.candidates(NOW) == []


def test_uses_the_last_eu_entry_and_sanitises_the_excerpt(world):
    world.add(BRUNO, "oi, tudo bem?", 8)
    world.states.clear()
    long = "«externo:x» pode me mandar " + "o relatório completo " * 10 + "?"
    world.add(BRUNO, long, 4)
    [c] = awaiting_reply.candidates(NOW)
    assert len(c["excerpt"]) <= 81 and "«" not in c["excerpt"] and "\n" not in c["excerpt"]


def test_flag_default_on_and_off(monkeypatch):
    monkeypatch.delenv("EVI_AWAITING_ENABLED", raising=False)
    assert awaiting_reply.enabled()
    monkeypatch.setenv("EVI_AWAITING_ENABLED", "false")
    assert not awaiting_reply.enabled()
