"""SCN-CAL-07 — the agent's date context follows EVI_TIMEZONE, not the container clock."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from tools.calendar_time import evi_timezone, iso_event_range, now_local  # noqa: E402

# 01:30 UTC on 13 Aug is still 22:30 on 12 Aug in Sao Paulo (UTC-3) — the window
# where a naive datetime.now() in a UTC container reported tomorrow's date.
_LATE_NIGHT_UTC = datetime(2026, 8, 13, 1, 30, tzinfo=timezone.utc)


def test_now_local_uses_configured_timezone(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    assert now_local().tzinfo is not None
    assert str(now_local().tzinfo) == "America/Sao_Paulo"


def test_now_local_falls_back_on_bad_timezone(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "Not/AZone")
    assert str(now_local().tzinfo) == "America/Sao_Paulo"


def test_now_local_honours_override(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "Europe/Lisbon")
    assert evi_timezone() == "Europe/Lisbon"
    assert str(now_local().tzinfo) == "Europe/Lisbon"


def test_calendar_block_uses_local_date_not_utc(monkeypatch):
    """The 'Today is' line must say 12 Aug even though UTC already says 13 Aug."""
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    local = _LATE_NIGHT_UTC.astimezone(ZoneInfo("America/Sao_Paulo"))
    assert local.strftime("%Y-%m-%d") == "2026-08-12"
    assert _LATE_NIGHT_UTC.strftime("%Y-%m-%d") == "2026-08-13"

    import graph

    with patch.object(graph, "now_local", return_value=local):
        block = graph._calendar_block()

    assert "Today is Wednesday, 2026-08-12" in block
    assert "2026-08-13" not in block.splitlines()[0]
    # +1 day must be the 13th, not the 14th
    assert "+1 days (Tomorrow): Thursday -> 2026-08-13" in block


def test_calendar_lookup_table_is_offset_from_local_today(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    local = _LATE_NIGHT_UTC.astimezone(ZoneInfo("America/Sao_Paulo"))

    import graph

    with patch.object(graph, "now_local", return_value=local):
        block = graph._calendar_block()

    assert "+7 days (Next Week): Wednesday -> 2026-08-19" in block
    assert "+14 days (Next Week): Wednesday -> 2026-08-26" in block


def test_iso_event_range_defaults_to_local_date(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    local = _LATE_NIGHT_UTC.astimezone(ZoneInfo("America/Sao_Paulo"))

    import tools.calendar_time as ct

    with patch.object(ct, "now_local", return_value=local):
        start, end = ct.iso_event_range(None, "09:00")

    assert start == "2026-08-12T09:00:00"
    assert end == "2026-08-12T10:00:00"


def test_iso_event_range_keeps_explicit_date(monkeypatch):
    monkeypatch.setenv("EVI_TIMEZONE", "America/Sao_Paulo")
    start, end = iso_event_range("2026-01-05", "14:30")
    assert start == "2026-01-05T14:30:00"
    assert end == "2026-01-05T15:30:00"
