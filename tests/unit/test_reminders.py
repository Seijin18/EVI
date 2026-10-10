"""evi-reminders: validation, recurrence, formatting and the fire tick (SCN-REM-03/05)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from services import reminders as R

SP = ZoneInfo("America/Sao_Paulo")
NY = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def _tz(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")


# --- validate_new ---------------------------------------------------------------

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=SP)


def test_validate_naive_iso_uses_evi_timezone():
    dt, err = R.validate_new("x", "2026-10-10T18:00", None, NOW)
    assert err is None and dt == datetime(2026, 10, 10, 18, 0, tzinfo=SP)


def test_validate_offset_kept_and_past_tolerance():
    dt, err = R.validate_new("x", "2026-10-10T14:59:30+00:00", "daily", NOW)  # 11:59:30 local
    assert err is None and dt is not None
    dt, err = R.validate_new("x", "2026-10-10T11:00", None, NOW)
    assert dt is None and err


@pytest.mark.parametrize("text,due,repeat", [
    ("", "2026-10-11T10:00", None),
    ("   ", "2026-10-11T10:00", None),
    ("x", "amanhã", None),
    ("x", "2026-10-11T10:00", "yearly"),
    ("x", "2027-10-12T10:00", None),  # > 1 year
])
def test_validate_rejects(text, due, repeat):
    dt, err = R.validate_new(text, due, repeat, NOW)
    assert dt is None and err


def test_validate_one_year_boundary_ok():
    dt, err = R.validate_new("x", "2027-10-09T12:00", "monthly", NOW)
    assert err is None


# --- next_occurrence ------------------------------------------------------------

def test_daily_overdue_three_days_advances_to_next_future_0800():
    due = datetime(2026, 10, 7, 8, 0, tzinfo=SP)
    now = datetime(2026, 10, 10, 10, 0, tzinfo=SP)
    assert R.next_occurrence(due, "daily", now) == datetime(2026, 10, 11, 8, 0, tzinfo=SP)
    now = datetime(2026, 10, 10, 7, 0, tzinfo=SP)
    assert R.next_occurrence(due, "daily", now) == datetime(2026, 10, 10, 8, 0, tzinfo=SP)


def test_strictly_after():
    due = datetime(2026, 10, 10, 8, 0, tzinfo=SP)
    assert R.next_occurrence(due, "daily", due) == due + timedelta(days=1)


def test_weekdays_skips_weekend():
    fri = datetime(2026, 10, 9, 9, 0, tzinfo=SP)  # Friday
    assert R.next_occurrence(fri, "weekdays", fri) == datetime(2026, 10, 12, 9, 0, tzinfo=SP)
    sat = datetime(2026, 10, 10, 9, 0, tzinfo=SP)
    assert R.next_occurrence(fri, "weekdays", sat) == datetime(2026, 10, 12, 9, 0, tzinfo=SP)


def test_weekly_keeps_weekday_when_overdue():
    due = datetime(2026, 9, 1, 7, 30, tzinfo=SP)  # Tuesday
    now = datetime(2026, 10, 10, 12, 0, tzinfo=SP)  # Saturday
    nxt = R.next_occurrence(due, "weekly", now)
    assert nxt == datetime(2026, 10, 13, 7, 30, tzinfo=SP) and nxt.weekday() == 1


def test_monthly_plain_and_month_end():
    due = datetime(2026, 1, 15, 9, 0, tzinfo=SP)
    assert R.next_occurrence(due, "monthly", due) == datetime(2026, 2, 15, 9, 0, tzinfo=SP)
    jan31 = datetime(2026, 1, 31, 9, 0, tzinfo=SP)
    assert R.next_occurrence(jan31, "monthly", jan31) == datetime(2026, 2, 28, 9, 0, tzinfo=SP)
    # leap year
    jan31 = datetime(2028, 1, 31, 9, 0, tzinfo=SP)
    assert R.next_occurrence(jan31, "monthly", jan31) == datetime(2028, 2, 29, 9, 0, tzinfo=SP)
    # year rollover
    dec = datetime(2026, 12, 20, 9, 0, tzinfo=SP)
    assert R.next_occurrence(dec, "monthly", dec) == datetime(2027, 1, 20, 9, 0, tzinfo=SP)


def test_monthly_anchor_returns_to_31st():
    jan31 = datetime(2026, 1, 31, 9, 0, tzinfo=SP)
    feb = R.next_occurrence(jan31, "monthly", jan31, anchor_day=31)
    assert feb == datetime(2026, 2, 28, 9, 0, tzinfo=SP)
    mar = R.next_occurrence(feb, "monthly", feb, anchor_day=31)
    assert mar == datetime(2026, 3, 31, 9, 0, tzinfo=SP)
    apr = R.next_occurrence(mar, "monthly", mar, anchor_day=31)
    assert apr == datetime(2026, 4, 30, 9, 0, tzinfo=SP)
    # without the anchor the clamped day sticks (why the column exists)
    assert R.next_occurrence(feb, "monthly", feb) == datetime(2026, 3, 28, 9, 0, tzinfo=SP)


def test_fire_due_passes_anchor_day(fake_db):
    due = datetime(2026, 2, 28, 9, 0, tzinfo=SP)
    fake_db.claim_due.return_value = [_row(repeat="monthly", due_at=due, anchor_day=31)]
    R.fire_due(now=due + timedelta(seconds=5), send=lambda t, c: True)
    assert fake_db.finish_fired.call_args.kwargs["next_due_at"] == datetime(2026, 3, 31, 9, 0, tzinfo=SP)


def test_monthly_overdue_many_months():
    due = datetime(2026, 1, 15, 9, 0, tzinfo=SP)
    now = datetime(2026, 10, 10, 12, 0, tzinfo=SP)
    assert R.next_occurrence(due, "monthly", now) == datetime(2026, 10, 15, 9, 0, tzinfo=SP)


def test_dst_wall_clock_preserved(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/New_York")
    due = datetime(2026, 3, 7, 8, 0, tzinfo=NY)  # EST, day before spring forward
    nxt = R.next_occurrence(due, "daily", due)
    assert nxt == datetime(2026, 3, 8, 8, 0, tzinfo=NY)
    assert nxt.astimezone(timezone.utc).hour == 12  # EDT: 08:00 local = 12:00Z (was 13:00Z)
    nxt = R.next_occurrence(due, "weekly", due)
    assert nxt.astimezone(NY).hour == 8 and nxt.astimezone(timezone.utc).hour == 12
    fall = datetime(2026, 10, 31, 8, 0, tzinfo=NY)  # EDT -> EST next day
    nxt = R.next_occurrence(fall, "daily", fall)
    assert nxt.astimezone(NY).hour == 8 and nxt.astimezone(timezone.utc).hour == 13


def test_next_occurrence_unknown_repeat():
    with pytest.raises(ValueError):
        R.next_occurrence(NOW, "hourly", NOW)


# --- format_reminder ------------------------------------------------------------

def test_format_on_time_and_just_inside_window():
    row = {"text": "pagar boleto", "due_at": NOW}
    assert R.format_reminder(row, NOW + timedelta(seconds=40)) == "⏰ Lembrete: pagar boleto"
    assert "atrasado" not in R.format_reminder(row, NOW + timedelta(minutes=5))


def test_format_late_same_day_and_other_day():
    due = datetime(2026, 10, 10, 18, 0, tzinfo=SP)
    row = {"text": "ligar", "due_at": due.astimezone(timezone.utc)}
    now = datetime(2026, 10, 10, 21, 0, tzinfo=SP)
    assert R.format_reminder(row, now) == "⏰ Lembrete (atrasado, era 18:00): ligar"
    later = datetime(2026, 10, 12, 9, 0, tzinfo=SP)
    assert R.format_reminder(row, later) == "⏰ Lembrete (atrasado, era 10/10 18:00): ligar"


# --- fire_due -------------------------------------------------------------------

@pytest.fixture
def fake_db(monkeypatch):
    m = MagicMock()
    m.claim_due.return_value = []
    R._pending_finish.clear()
    R._warned_not_configured = False
    monkeypatch.setattr(R, "db", m)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return m


def _row(**kw):
    base = {"id": 7, "text": "tomar remédio", "chat_id": "42", "repeat": None,
            "due_at": datetime(2026, 10, 10, 18, 0, tzinfo=SP)}
    base.update(kw)
    return base


def test_fire_one_off_late_scn_rem_05(fake_db, monkeypatch):
    mem = MagicMock()
    monkeypatch.setattr("services.session_memory.get_session_memory", lambda sid: mem)
    now = datetime(2026, 10, 10, 21, 0, tzinfo=SP)
    fake_db.claim_due.return_value = [_row()]
    send = MagicMock(return_value=True)
    out = R.fire_due(now=now, send=send)
    assert out == {"claimed": 1, "sent": 1, "failed": 0, "late": 1}
    sent_text = send.call_args.args[0]
    assert "atrasado" in sent_text and "18:00" in sent_text
    assert send.call_args.args[1] == "42"
    fake_db.finish_fired.assert_called_once_with(7, now, 3 * 3600, next_due_at=None)
    fake_db.init_db.assert_called_once()
    fake_db.save_tool_snapshot.assert_called_once_with(
        "telegram-42", "last_reminder", {"id": 7, "text": "tomar remédio"})
    assert mem.add.call_args.args[0].content == sent_text
    fake_db.release_reminder.assert_not_called()
    fake_db.requeue_stuck.assert_called_once_with(5)


def test_fire_persists_message_with_database_url(fake_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setattr("services.session_memory.get_session_memory", lambda sid: MagicMock())
    fake_db.claim_due.return_value = [_row()]
    now = datetime(2026, 10, 10, 18, 0, 5, tzinfo=SP)
    out = R.fire_due(now=now, send=lambda t, c: True)
    assert out["late"] == 0
    fake_db.save_message.assert_called_once_with("telegram-42", "assistant", "⏰ Lembrete: tomar remédio")


def test_recurring_three_days_late_fires_once_and_advances_scn_rem_03(fake_db):
    due = datetime(2026, 10, 7, 8, 0, tzinfo=SP)
    now = datetime(2026, 10, 10, 10, 0, tzinfo=SP)
    fake_db.claim_due.return_value = [_row(repeat="daily", due_at=due)]
    send = MagicMock(return_value=True)
    out = R.fire_due(now=now, send=send)
    assert send.call_count == 1 and out["sent"] == 1 and out["late"] == 1
    assert "atrasado" in send.call_args.args[0]
    (rid, fired_at, drift), kw = fake_db.finish_fired.call_args
    assert rid == 7 and fired_at == now and drift == int((now - due).total_seconds())
    assert kw["next_due_at"] == datetime(2026, 10, 11, 8, 0, tzinfo=SP)


def test_send_failure_releases_and_does_not_finish(fake_db):
    fake_db.claim_due.return_value = [_row(id=1), _row(id=2)]
    send = MagicMock(side_effect=[False, RuntimeError("boom")])
    out = R.fire_due(now=datetime(2026, 10, 10, 18, 1, tzinfo=SP), send=send)
    assert out == {"claimed": 2, "sent": 0, "failed": 2, "late": 0}
    assert [c.args[0] for c in fake_db.release_reminder.call_args_list] == [1, 2]
    fake_db.finish_fired.assert_not_called()
    fake_db.save_tool_snapshot.assert_not_called()


def test_side_effect_failures_do_not_break_tick(fake_db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setattr("services.session_memory.get_session_memory",
                        MagicMock(side_effect=RuntimeError("mem")))
    fake_db.save_message.side_effect = RuntimeError("db")
    fake_db.save_tool_snapshot.side_effect = RuntimeError("db")
    fake_db.requeue_stuck.side_effect = RuntimeError("db")
    fake_db.claim_due.return_value = [_row(id=1), _row(id=2)]
    out = R.fire_due(now=datetime(2026, 10, 10, 18, 0, 1, tzinfo=SP), send=lambda t, c: True)
    assert out["sent"] == 2
    assert fake_db.finish_fired.call_count == 2


def test_claim_failure_returns_zero_counts(fake_db):
    fake_db.claim_due.side_effect = RuntimeError("down")
    assert R.fire_due(now=NOW, send=lambda t, c: True) == {
        "claimed": 0, "sent": 0, "failed": 0, "late": 0}


def test_metrics_helper_records(monkeypatch):
    from services import metrics

    monkeypatch.setenv("EVI_METRICS_ENABLED", "true")
    metrics.record_reminder_fired(True, 400)
    metrics.record_reminder_fired(False, 2)


# --- review fixes: snooze, finish retry, NOT_CONFIGURED, per-send clock ---------

def test_snoozed_recurring_fire_keeps_series_and_measures_drift_from_snooze(fake_db):
    """daily 08:00 + 'adia 1h': row already rescheduled to tomorrow 08:00, snooze_until 09:00."""
    tomorrow = datetime(2026, 10, 11, 8, 0, tzinfo=SP)
    snooze = datetime(2026, 10, 10, 9, 0, tzinfo=SP)
    now = datetime(2026, 10, 10, 9, 0, 10, tzinfo=SP)
    fake_db.claim_due.return_value = [_row(repeat="daily", due_at=tomorrow, snooze_until=snooze)]
    send = MagicMock(return_value=True)
    out = R.fire_due(now=now, send=send)
    assert out["late"] == 0 and send.call_args.args[0] == "⏰ Lembrete: tomar remédio"
    (rid, fired_at, drift), kw = fake_db.finish_fired.call_args
    assert drift == 10 and kw["next_due_at"] == tomorrow  # not advanced twice


def test_snoozed_weekly_keeps_weekday(fake_db):
    nxt_week = datetime(2026, 10, 13, 7, 30, tzinfo=SP)  # Tuesday
    snooze = datetime(2026, 10, 11, 7, 30, tzinfo=SP)  # "para amanhã" (Sunday)
    fake_db.claim_due.return_value = [_row(repeat="weekly", due_at=nxt_week, snooze_until=snooze)]
    R.fire_due(now=snooze + timedelta(seconds=3), send=lambda t, c: True)
    assert fake_db.finish_fired.call_args.kwargs["next_due_at"] == nxt_week
    assert nxt_week.weekday() == 1


def test_snoozed_pending_recurring_past_due_advances_from_anchor(fake_db):
    due = datetime(2026, 10, 10, 8, 0, tzinfo=SP)
    snooze = datetime(2026, 10, 10, 9, 0, tzinfo=SP)
    fake_db.claim_due.return_value = [_row(repeat="daily", due_at=due, snooze_until=snooze)]
    R.fire_due(now=snooze, send=lambda t, c: True)
    assert fake_db.finish_fired.call_args.kwargs["next_due_at"] == datetime(2026, 10, 11, 8, 0, tzinfo=SP)


def test_finish_failure_retried_then_pending_finish_without_resend(fake_db):
    now = datetime(2026, 10, 10, 18, 0, 5, tzinfo=SP)
    fake_db.claim_due.return_value = [_row()]
    fake_db.finish_fired.side_effect = RuntimeError("db down")
    send = MagicMock(return_value=True)
    R.fire_due(now=now, send=send)
    assert fake_db.finish_fired.call_count == 3 and send.call_count == 1
    assert len(R._pending_finish) == 1
    # next tick: db back; finish happens first, before requeue_stuck, no resend
    order = []
    fake_db.finish_fired.reset_mock(side_effect=True)
    fake_db.finish_fired.side_effect = lambda *a, **k: order.append("finish")
    fake_db.requeue_stuck.side_effect = lambda *a, **k: order.append("requeue")
    fake_db.claim_due.return_value = []
    R.fire_due(now=now + timedelta(seconds=30), send=send)
    assert order == ["finish", "requeue"] and send.call_count == 1
    assert R._pending_finish == []


def test_finish_succeeds_on_retry(fake_db):
    fake_db.claim_due.return_value = [_row()]
    fake_db.finish_fired.side_effect = [RuntimeError("x"), None]
    R.fire_due(now=datetime(2026, 10, 10, 18, 0, 5, tzinfo=SP), send=lambda t, c: True)
    assert fake_db.finish_fired.call_count == 2 and R._pending_finish == []


def test_not_configured_marks_failed_not_released(fake_db):
    from services.send_result import SendResult, NOT_CONFIGURED

    fake_db.claim_due.return_value = [_row(id=1), _row(id=2)]
    send = MagicMock(return_value=SendResult.fail(NOT_CONFIGURED, detail="missing"))
    out = R.fire_due(now=datetime(2026, 10, 10, 18, 1, tzinfo=SP), send=send)
    assert out["failed"] == 2 and out["sent"] == 0
    assert [c.args[0] for c in fake_db.fail_reminder.call_args_list] == [1, 2]
    fake_db.release_reminder.assert_not_called()
    fake_db.finish_fired.assert_not_called()


def test_transport_failure_still_releases(fake_db):
    from services.send_result import SendResult, TRANSPORT

    fake_db.claim_due.return_value = [_row()]
    R.fire_due(now=NOW, send=lambda t, c: SendResult.fail(TRANSPORT))
    fake_db.release_reminder.assert_called_once_with(7)
    fake_db.fail_reminder.assert_not_called()


def test_fired_at_and_drift_reread_after_each_send(fake_db, monkeypatch):
    t0 = datetime(2026, 10, 10, 18, 0, 1, tzinfo=SP)
    clock = iter([t0, t0 + timedelta(seconds=10), t0 + timedelta(seconds=20)])
    monkeypatch.setattr(R, "now_local", lambda: next(clock))
    fake_db.claim_due.return_value = [_row(id=1), _row(id=2)]
    R.fire_due(send=lambda t, c: True)
    drifts = [c.args[2] for c in fake_db.finish_fired.call_args_list]
    assert drifts == [11, 21]
