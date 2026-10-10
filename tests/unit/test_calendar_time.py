"""Unit tests for calendar timezone normalization."""

import os
import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from tools.calendar_time import evi_timezone, iso_event_range, normalize_wall_clock  # noqa: E402


def test_normalize_strips_z():
    assert normalize_wall_clock("2026-06-10T09:00:00Z") == "2026-06-10T09:00:00"


def test_iso_range_no_utc_suffix():
    start, end = iso_event_range("2026-06-10", "09:00")
    assert start == "2026-06-10T09:00:00"
    assert end == "2026-06-10T10:00:00"
    assert "Z" not in start


def test_evi_timezone_default():
    os.environ.pop("EVI_TIMEZONE", None)
    assert evi_timezone() == "America/Sao_Paulo"


if __name__ == "__main__":
    test_normalize_strips_z()
    test_iso_range_no_utc_suffix()
    test_evi_timezone_default()
    print("ok")


def test_schedule_event_default_end_is_one_hour_after_start():
    """No end time from the user → 1 h event, no clarification round-trip."""
    from tools.calendar_tool import _default_end

    assert _default_end("2026-10-11T10:00:00") == "2026-10-11T11:00:00"
    assert _default_end("2026-10-11T23:30") == "2026-10-12T00:30:00"
    assert _default_end("2026-10-11T10:00:00-03:00") == "2026-10-11T11:00:00"
    assert _default_end("amanhã") == "amanhã"
