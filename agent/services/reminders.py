"""Reminders: validation, recurrence and the due-tick (evi-reminders).

Pure helpers (validate_new, next_occurrence, format_reminder) plus fire_due(), which
claims due rows atomically, delivers them on Telegram and records the outcome. Every
side effect around the send is soft-failed; only a failed send releases the row.
"""

from __future__ import annotations

import calendar
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import db
from services.send_result import NOT_CONFIGURED
from services.soft_fail import soft_fail
from tools.calendar_time import evi_timezone, now_local

REPEATS = ("daily", "weekdays", "weekly", "monthly")
LATE_AFTER_S = 300
PAST_TOLERANCE = timedelta(minutes=1)
MAX_AHEAD = timedelta(days=366)


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(evi_timezone())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/Sao_Paulo")


def validate_new(text, due_at, repeat, now: datetime) -> tuple[datetime | None, str | None]:
    """Return (due_at aware, None) or (None, error message)."""
    if not isinstance(text, str) or not text.strip():
        return None, "O texto do lembrete não pode ser vazio."
    if repeat not in (None, "") and repeat not in REPEATS:
        return None, f"Repetição inválida: use {', '.join(REPEATS)} ou nenhuma."
    if isinstance(due_at, datetime):
        dt = due_at
    else:
        try:
            dt = datetime.fromisoformat(str(due_at).strip().replace("Z", "+00:00"))
        except ValueError:
            return None, "Data/hora inválida: use o formato ISO, ex. 2026-10-10T18:00."
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz())
    if now.tzinfo is None:
        now = now.replace(tzinfo=_tz())
    if dt < now - PAST_TOLERANCE:
        return None, "Essa data/hora já passou."
    if dt > now + MAX_AHEAD:
        return None, "O lembrete pode ser agendado no máximo 1 ano à frente."
    return dt, None


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + n
    return idx // 12, idx % 12 + 1


def _local_candidate(d, wall_time, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, wall_time).replace(tzinfo=tz)


def next_occurrence(
    due_at: datetime, repeat: str, after: datetime, anchor_day: int | None = None
) -> datetime:
    """First occurrence of the recurrence strictly after ``after``, wall-clock preserved.

    Computed on local dates in EVI_TIMEZONE (so DST shifts never move the time of day)
    and returned aware. A monthly (anchored on ``anchor_day``, default the day of ``due_at``) reminder anchored on day N uses the month's last day
    when the month is shorter.
    """
    if repeat not in REPEATS:
        raise ValueError(f"unknown repeat: {repeat!r}")
    tz = _tz()
    start = due_at.astimezone(tz)
    after_l = after.astimezone(tz)
    wall = start.timetz().replace(tzinfo=None)
    anchor_day = anchor_day or start.day

    def ok(c: datetime) -> bool:
        # compare by UTC instant: wall time in a DST gap is normalised by astimezone
        return c.astimezone(timezone.utc) > after_l.astimezone(timezone.utc)

    if repeat == "monthly":
        y, m = start.year, start.month
        # jump near `after` instead of iterating month by month
        months = (after_l.year - y) * 12 + (after_l.month - m)
        y, m = _add_months(y, m, max(0, months - 1))
        for _ in range(30):
            day = min(anchor_day, calendar.monthrange(y, m)[1])
            cand = _local_candidate(datetime(y, m, day).date(), wall, tz)
            if ok(cand) and cand.astimezone(timezone.utc) > start.astimezone(timezone.utc):
                return cand
            y, m = _add_months(y, m, 1)
        raise RuntimeError("monthly recurrence did not converge")

    d = max(start.date(), (after_l - timedelta(days=1)).date())
    step = 7 if repeat == "weekly" else 1
    if repeat == "weekly":
        # keep the original weekday
        d = start.date() + timedelta(days=((d - start.date()).days // 7) * 7)
    for _ in range(800):
        cand = _local_candidate(d, wall, tz)
        weekday_ok = repeat != "weekdays" or d.weekday() < 5
        if weekday_ok and ok(cand) and cand.astimezone(timezone.utc) > start.astimezone(timezone.utc):
            return cand
        d += timedelta(days=step)
    raise RuntimeError("recurrence did not converge")


def format_reminder(row: dict, now: datetime) -> str:
    """'⏰ Lembrete: text', or the 'atrasado' variant when delivered >5 min after due_at."""
    text = row["text"]
    due = row["due_at"]
    if (now - due).total_seconds() <= LATE_AFTER_S:
        return f"⏰ Lembrete: {text}"
    tz = _tz()
    due_l = due.astimezone(tz)
    when = due_l.strftime("%H:%M")
    if due_l.date() != now.astimezone(tz).date():
        when = f"{due_l.strftime('%d/%m')} {when}"
    return f"⏰ Lembrete (atrasado, era {when}): {text}"


def _telegram_session_id(chat_id: str) -> str:
    return f"telegram-{chat_id}"


def _record_delivery(row: dict, text: str) -> None:
    """History + snapshot so 'feito' / 'adia 1h' can resolve the reminder id."""
    session_id = _telegram_session_id(row["chat_id"])
    try:
        from langchain_core.messages import AIMessage

        from services.session_memory import get_session_memory

        get_session_memory(session_id).add(AIMessage(content=text))
    except Exception as exc:
        soft_fail("reminders.fire.memory", exc)
    if os.getenv("DATABASE_URL"):
        try:
            db.save_message(session_id, "assistant", text)
        except Exception as exc:
            soft_fail("reminders.fire.persist_message", exc)
    try:
        db.save_tool_snapshot(
            session_id, "last_reminder", {"id": row["id"], "text": row["text"]}
        )
    except Exception as exc:
        soft_fail("reminders.fire.snapshot", exc)


# Delivered occurrences whose finish_fired kept failing: (id, fired_at, drift_s, next_due_at).
# Finished at the start of the next tick, before requeue_stuck, so they are never re-sent.
_pending_finish: list[tuple] = []
_FINISH_ATTEMPTS = 3
_warned_not_configured = False


def _finish_with_retry(rid, fired_at, drift_s, nxt) -> bool:
    for attempt in range(_FINISH_ATTEMPTS):
        try:
            db.finish_fired(rid, fired_at, drift_s, next_due_at=nxt)
            return True
        except Exception as exc:
            soft_fail("reminders.fire.finish", exc, detail=f"id={rid} attempt={attempt + 1}")
    return False


def _flush_pending_finish() -> None:
    for item in list(_pending_finish):
        try:
            db.finish_fired(item[0], item[1], item[2], next_due_at=item[3])
        except Exception as exc:
            soft_fail("reminders.fire.finish_pending", exc, detail=f"id={item[0]}")
            continue
        _pending_finish.remove(item)


def _next_after_fire(row: dict, fired_at: datetime):
    """Next due_at for a recurring row after a delivery (None for one-off).

    A snoozed fire of a row already rescheduled past ``fired_at`` keeps its due_at
    (don't advance twice); otherwise recurrence runs from the series anchor.
    """
    if not row.get("repeat"):
        return None
    if row.get("snooze_until") and row["due_at"] > fired_at:
        return row["due_at"]
    return next_occurrence(row["due_at"], row["repeat"], fired_at, row.get("anchor_day"))


def fire_due(now: datetime | None = None, send: Callable[..., Any] | None = None) -> dict:
    """One tick: claim due reminders, deliver, advance/close. Returns counts.

    An explicit ``now`` pins the clock (tests); otherwise it is re-read after each send.
    """
    global _warned_not_configured
    if send is None:
        from services.telegram_notify import send_telegram_message as send
    pinned = now is not None
    now = now or now_local()
    counts = {"claimed": 0, "sent": 0, "failed": 0, "late": 0}
    try:
        db.init_db()
    except Exception as exc:
        soft_fail("reminders.fire.init_db", exc)
    _flush_pending_finish()
    try:
        db.requeue_stuck(5)
    except Exception as exc:
        soft_fail("reminders.fire.requeue", exc)
    try:
        rows = db.claim_due(now)
    except Exception as exc:
        soft_fail("reminders.fire.claim", exc)
        return counts
    counts["claimed"] = len(rows)
    for row in rows:
        rid = row["id"]
        # a snoozed fire is measured against the snooze time, not the series anchor
        scheduled = row.get("snooze_until") or row["due_at"]
        eff = {**row, "due_at": scheduled}
        reason = ""
        try:
            text = format_reminder(eff, now)
            res = send(text, row["chat_id"])
            ok = bool(res)
            reason = getattr(res, "reason", "") or ""
        except Exception as exc:
            soft_fail("reminders.fire.send", exc)
            ok = False
        if not ok:
            counts["failed"] += 1
            try:
                if reason == NOT_CONFIGURED:
                    if not _warned_not_configured:
                        _warned_not_configured = True
                        soft_fail("reminders.fire.not_configured",
                                  RuntimeError("telegram not configured"), detail=f"id={rid}")
                    db.fail_reminder(rid)
                else:
                    db.release_reminder(rid)
            except Exception as exc:
                soft_fail("reminders.fire.release", exc)
            continue
        counts["sent"] += 1
        fired_at = now if pinned else now_local()
        drift_s = int((fired_at - scheduled).total_seconds())
        late = drift_s > LATE_AFTER_S
        if late:
            counts["late"] += 1
        _record_delivery(row, text)
        try:
            nxt = _next_after_fire(row, fired_at)
        except Exception as exc:
            soft_fail("reminders.fire.next", exc, detail=f"id={rid}")
            nxt = fired_at + timedelta(days=1) if row.get("repeat") else None
        if not _finish_with_retry(rid, fired_at, drift_s, nxt):
            # delivered but not closed: keep it so the next tick finishes without re-sending
            _pending_finish.append((rid, fired_at, drift_s, nxt))
        try:
            from services import metrics

            metrics.record_reminder_fired(late, drift_s)
        except Exception as exc:
            soft_fail("reminders.fire.metrics", exc)
    return counts
