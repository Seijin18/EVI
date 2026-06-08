"""Unit tests for services/commitment_review/digest.py."""

import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.commitment_review.digest import format_pending_digest, format_scheduled_today  # noqa: E402


def _make_row(id, title, priority="normal", event_date="2026-06-10", source_label="Work"):
    return {
        "id": id,
        "title": title,
        "priority": priority,
        "event_date": event_date,
        "source_label": source_label,
    }


def test_format_pending_digest_basic():
    rows = [_make_row(1, "Reunião"), _make_row(2, "Almoço", priority="high")]
    out = format_pending_digest(rows)
    assert "[1]" in out
    assert "[2]" in out
    assert "Reunião" in out
    assert "high" in out
    assert "Work" in out
    assert "confirmar" in out.lower()


def test_format_pending_digest_caps_at_10():
    rows = [_make_row(i, f"Item {i}") for i in range(15)]
    out = format_pending_digest(rows)
    assert "Item 10" not in out
    assert "Item 9" in out


def test_format_scheduled_today_basic():
    rows = [
        {"id": 1, "title": "Almoço", "event_time": "12:00", "source_label": "João", "confirmed_via": "whatsapp"},
    ]
    out = format_scheduled_today(rows)
    assert "Almoço" in out
    assert "12:00" in out
    assert "João" in out
    assert "whatsapp" in out


def test_format_scheduled_today_empty():
    out = format_scheduled_today([])
    assert "Nenhum" in out


def test_telegram_notify_reexport():
    """telegram_notify.format_pending_digest must be the same as digest.format_pending_digest."""
    from services.telegram_notify import format_pending_digest as tg_fn
    from services.commitment_review.digest import format_pending_digest as dig_fn
    assert tg_fn is dig_fn


if __name__ == "__main__":
    test_format_pending_digest_basic()
    test_format_pending_digest_caps_at_10()
    test_format_scheduled_today_basic()
    test_format_scheduled_today_empty()
    test_telegram_notify_reexport()
    print("ok")
