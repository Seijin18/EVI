"""Reminder tools (evi-reminders): the LLM creates, lists, snoozes and closes reminders."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from tools.calendar_time import evi_timezone, now_local

_DISABLED = "Lembretes estão desativados (EVI_REMINDERS_ENABLED)."
_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
_REPEAT_LABEL = {
    "daily": "diário",
    "weekdays": "dias úteis",
    "weekly": "semanal",
    "monthly": "mensal",
}


def _reminders_enabled() -> bool:
    # Read at call time so tests/ops can flip the flag without a restart.
    return os.getenv("EVI_REMINDERS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _local(dt: datetime) -> datetime:
    return dt.astimezone(ZoneInfo(evi_timezone()))


def _fmt_full(dt: datetime) -> str:
    d = _local(dt)
    return f"{_WEEKDAYS[d.weekday()]} {d:%d/%m} às {d:%H:%M}"


def _validate(text: str, due_at: str, repeat: str | None):
    from services.reminders import validate_new

    return validate_new(text, due_at, repeat, now_local())


@tool
def create_reminder(text: str, due_at: str, repeat: str = "") -> str:
    """Create a reminder that EVI sends on Telegram at the given time.

    Use when the user says "me lembra ...". Resolve relative times ("amanhã às 18h")
    from the calendar header and pass `due_at` as ISO 8601 LOCAL time, e.g.
    "2026-10-10T18:00:00". `repeat` is one of daily|weekdays|weekly|monthly, or
    empty for a one-off reminder. `text` is just what to remind about.
    """
    if not _reminders_enabled():
        return _DISABLED
    text = (text or "").strip()
    if not text:
        return "Não consegui criar o lembrete: texto vazio."
    rep = (repeat or "").strip().lower() or None
    try:
        due, err = _validate(text, due_at, rep)
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui validar o lembrete: {exc}"
    if err:
        return f"Não criei o lembrete: {err}"

    from db import create_reminder as _create, init_db

    init_db()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    try:
        _create(text, due, rep, chat_id, "telegram")
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui salvar o lembrete: {exc}"
    suffix = f" ({_REPEAT_LABEL[rep]})" if rep in _REPEAT_LABEL else ""
    return f"Lembrete para {_fmt_full(due)}: {text}{suffix}"


@tool
def list_reminders() -> str:
    """List pending reminders (id, local date/time, text, repetition)."""
    if not _reminders_enabled():
        return _DISABLED
    from db import init_db, list_reminders as _list

    init_db()
    rows = _list(chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip() or None)
    if not rows:
        return "Nenhum lembrete pendente."
    lines = []
    for r in rows:
        rep = f" ({_REPEAT_LABEL.get(r.get('repeat') or '', r['repeat'])})" if r.get("repeat") else ""
        lines.append(f"#{r['id']} {_fmt_full(r['due_at'])}: {r['text']}{rep}")
    return "\n".join(lines)


@tool
def cancel_reminder(reminder_id: int) -> str:
    """Cancel a pending reminder by id (see list_reminders)."""
    if not _reminders_enabled():
        return _DISABLED
    from db import cancel_reminder as _cancel, init_db

    init_db()
    if _cancel(int(reminder_id)):
        return f"Lembrete #{int(reminder_id)} cancelado."
    return f"Lembrete #{int(reminder_id)} não encontrado ou já encerrado."


@tool
def complete_reminder(reminder_id: int) -> str:
    """Mark a reminder as done. Use when the user answers "feito"/"ok" after a
    delivered reminder; its id is in the `last_reminder` snapshot. A recurring
    reminder stops recurring."""
    if not _reminders_enabled():
        return _DISABLED
    from db import complete_reminder as _complete, init_db

    init_db()
    if _complete(int(reminder_id)):
        return f"Lembrete #{int(reminder_id)} concluído."
    return f"Lembrete #{int(reminder_id)} não encontrado ou já encerrado."


@tool
def snooze_reminder(reminder_id: int, until: str) -> str:
    """Postpone a reminder to a new time. Use for "adia 1h"/"adia para amanhã"
    after a delivered reminder (id in the `last_reminder` snapshot). `until` is
    ISO 8601 LOCAL time resolved from the calendar header, e.g. "2026-10-10T19:00:00",
    and must be in the future."""
    if not _reminders_enabled():
        return _DISABLED
    try:
        when, err = _validate("snooze", until, None)
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui validar o horário: {exc}"
    if err:
        return f"Não adiei o lembrete: {err}"

    from db import init_db, snooze_reminder as _snooze

    init_db()
    if _snooze(int(reminder_id), when):
        return f"Lembrete #{int(reminder_id)} adiado para {_fmt_full(when)}."
    return f"Lembrete #{int(reminder_id)} não encontrado ou não pode ser adiado."
