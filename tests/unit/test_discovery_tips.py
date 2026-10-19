"""SCN-TIP-01/02 — discovery tip catalogue, rotation, flag and soft-fail; the turn_log
usage query (ephemeral Postgres only)."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

import db  # noqa: E402
from services import discovery_tips as dt  # noqa: E402

ALL_USED = {t.marker for t in dt.TIPS}


def test_catalogue_markers_and_examples():
    by_id = {t.id: t for t in dt.TIPS}
    assert by_id["reminder"].marker == "create_reminder" and "me lembra" in by_id["reminder"].text
    assert by_id["voice"].marker == "input_kind:voice"
    assert by_id["contact"].marker == "get_whatsapp_contact_info"
    assert by_id["buttons"].marker == "input_kind:button"
    assert all(t.text.startswith("💡 Dica:") for t in dt.TIPS)


def test_pick_tip_none_when_everything_was_used():
    assert dt.pick_tip(date(2026, 10, 10), ALL_USED) is None


def test_pick_tip_only_among_unused_and_rotates_daily():
    used = ALL_USED - {"create_reminder", "input_kind:voice"}
    seen = {dt.pick_tip(date(2026, 10, 1) + timedelta(days=i), used) for i in range(6)}
    assert seen == {t.text for t in dt.TIPS if t.marker in {"create_reminder", "input_kind:voice"}}
    d = date(2026, 10, 10)
    assert dt.pick_tip(d, used) == dt.pick_tip(d, used)  # deterministic per day
    assert dt.pick_tip(d, used) != dt.pick_tip(d + timedelta(days=1), used)


def test_tip_for_flag_off_and_db_failure(monkeypatch):
    monkeypatch.setattr(db, "capabilities_used_since", lambda since: set())
    assert dt.tip_for(date(2026, 10, 10)) is not None
    monkeypatch.setenv("EVI_BRIEFING_TIPS", "false")
    assert dt.tip_for(date(2026, 10, 10)) is None
    monkeypatch.setenv("EVI_BRIEFING_TIPS", "true")

    def boom(since):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "capabilities_used_since", boom)
    assert dt.tip_for(date(2026, 10, 10)) is None


def test_tip_for_asks_for_the_14_day_window(monkeypatch):
    seen = []
    monkeypatch.setattr(db, "capabilities_used_since", lambda since: seen.append(since) or set())
    now = datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc)
    dt.tip_for(date(2026, 10, 10), now)
    assert seen == [now - timedelta(days=14)]


# --- turn_log usage query (needs an ephemeral Postgres) ---------------------------------


@pytest.mark.ephemeral_db
def test_capabilities_used_since_reads_tools_and_input_kind_of_real_turns():
    db.reset_db_init_for_tests()
    db.init_db()
    sid = f"test-{uuid.uuid4().hex[:8]}"
    long_ago = datetime.now(timezone.utc) - timedelta(days=1)
    db.insert_turn(session_id=sid, channel="telegram", user_text="x", input_kind="voice",
                   tools=[{"name": "create_reminder", "ok": True, "reason": None, "ms": 3},
                          {"type": "direct", "tool": "schedule_event"}])
    db.insert_turn(session_id=sid, channel="telegram", user_text="y",
                   tools=[{"name": "get_whatsapp_contact_info", "ok": False, "reason": "x", "ms": 1}])
    db.insert_turn(session_id=sid, channel="telegram", user_text="z", is_test=True, input_kind="button",
                   tools=[{"name": "list_reminders", "ok": True, "ms": 1}])
    used = db.capabilities_used_since(long_ago)
    assert {"create_reminder", "input_kind:voice"} <= used
    assert "get_whatsapp_contact_info" not in used  # the tool failed
    assert "input_kind:button" not in used and "list_reminders" not in used  # test turn
    assert db.capabilities_used_since(datetime.now(timezone.utc) + timedelta(days=1)) == set()


@pytest.mark.ephemeral_db
def test_capabilities_used_since_ignores_scheduled_turns():
    db.reset_db_init_for_tests()
    db.init_db()
    sid = f"scheduled:{uuid.uuid4().hex[:6]}"
    db.insert_turn(session_id=sid, channel="scheduled", user_text="resuma", input_kind="text",
                   tools=[{"name": "summarize_inbox_zz", "ok": True, "ms": 1}])
    used = db.capabilities_used_since(datetime.now(timezone.utc) - timedelta(days=1))
    assert "summarize_inbox_zz" not in used
