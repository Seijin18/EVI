"""Unit tests for reminder tools (SCN-REM-01 creation, SCN-REM-04 snooze)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

import db  # noqa: E402
from tools import reminder_tools as rt  # noqa: E402

TZ = timezone(timedelta(hours=-3))
NOW = datetime(2026, 10, 10, 17, 0, tzinfo=TZ)


def _stub_validate(text, due_at, repeat, now):
    if repeat not in (None, "daily", "weekdays", "weekly", "monthly"):
        return None, "repetição inválida"
    due = datetime.fromisoformat(due_at).replace(tzinfo=TZ)
    if due < NOW - timedelta(minutes=1):
        return None, "o horário já passou"
    return due, None


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "true")
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    calls = {"create": [], "snooze": [], "rows": []}
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(
        db, "create_reminder",
        lambda *a: calls["create"].append(a) or 1,
    )
    monkeypatch.setattr(db, "list_reminders", lambda **k: calls["rows"])
    monkeypatch.setattr(db, "snooze_reminder", lambda i, u: calls["snooze"].append((i, u)) or True)
    monkeypatch.setattr(db, "complete_reminder", lambda i: i == 1)
    monkeypatch.setattr(db, "cancel_reminder", lambda i: i == 1)
    monkeypatch.setattr(rt, "_validate", lambda t, d, r: _stub_validate(t, d, r, NOW))
    return calls


def test_create_ok(fake):
    out = rt.create_reminder.invoke({"text": "pagar o boleto", "due_at": "2026-10-10T18:00:00"})
    assert out == "Lembrete para sáb 10/10 às 18:00: pagar o boleto"
    assert len(fake["create"]) == 1
    assert fake["create"][0][3:] == ("42", "telegram")


def test_create_repeat_suffix(fake):
    out = rt.create_reminder.invoke(
        {"text": "remédio", "due_at": "2026-10-11T08:00:00", "repeat": "daily"}
    )
    assert out.endswith("remédio (diário)")


def test_past_refused(fake):
    out = rt.create_reminder.invoke({"text": "x", "due_at": "2026-10-09T10:00:00"})
    assert "passou" in out and not fake["create"]


def test_invalid_repeat_refused(fake):
    out = rt.create_reminder.invoke({"text": "x", "due_at": "2026-10-10T18:00:00", "repeat": "hourly"})
    assert "inválida" in out and not fake["create"]


def test_flag_off_writes_nothing(fake, monkeypatch):
    monkeypatch.setenv("EVI_REMINDERS_ENABLED", "false")
    msg = "Lembretes estão desativados (EVI_REMINDERS_ENABLED)."
    assert rt.create_reminder.invoke({"text": "x", "due_at": "2026-10-10T18:00:00"}) == msg
    assert rt.list_reminders.invoke({}) == msg
    assert rt.cancel_reminder.invoke({"reminder_id": 1}) == msg
    assert rt.complete_reminder.invoke({"reminder_id": 1}) == msg
    assert rt.snooze_reminder.invoke({"reminder_id": 1, "until": "2026-10-10T19:00:00"}) == msg
    assert not fake["create"] and not fake["snooze"]


def test_list_empty_and_rows(fake):
    assert rt.list_reminders.invoke({}) == "Nenhum lembrete pendente."
    fake["rows"].append({"id": 3, "text": "boleto", "repeat": "weekly",
                         "due_at": datetime(2026, 10, 10, 21, 0, tzinfo=timezone.utc)})
    out = rt.list_reminders.invoke({})
    assert out == "#3 sáb 10/10 às 18:00: boleto (semanal)"


def test_cancel_complete_messages(fake):
    assert "cancelado" in rt.cancel_reminder.invoke({"reminder_id": 1})
    assert "não encontrado" in rt.cancel_reminder.invoke({"reminder_id": 9})
    assert "concluído" in rt.complete_reminder.invoke({"reminder_id": 1})
    assert "não encontrado" in rt.complete_reminder.invoke({"reminder_id": 9})


def test_snooze(fake):
    out = rt.snooze_reminder.invoke({"reminder_id": 1, "until": "2026-10-10T19:00:00"})
    assert "adiado para sáb 10/10 às 19:00" in out
    assert fake["snooze"][0][0] == 1
    past = rt.snooze_reminder.invoke({"reminder_id": 1, "until": "2026-10-01T19:00:00"})
    assert "passou" in past and len(fake["snooze"]) == 1


def test_registry_exposes_tools():
    from tools.registry import get_all_tools

    names = {t.name for t in get_all_tools()}
    assert {"create_reminder", "list_reminders", "cancel_reminder",
            "snooze_reminder", "complete_reminder"} <= names


def test_real_validate_integration(monkeypatch):
    pytest.importorskip("services.reminders")
    from services.reminders import validate_new

    now = datetime.now(TZ)
    due, err = validate_new("x", (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"), None, now)
    assert err is None and due.tzinfo is not None
    _, err = validate_new("x", (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"), None, now)
    assert err
    _, err = validate_new("x", (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"), "hourly", now)
    assert err
