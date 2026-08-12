"""Calendar datetime helpers — local wall clock + IANA timezone for Google API."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_OFFSET_SUFFIX = re.compile(r"([+-]\d{2}:\d{2}|Z)$")
_FALLBACK_TZ = "America/Sao_Paulo"


def evi_timezone() -> str:
    return os.getenv("EVI_TIMEZONE", _FALLBACK_TZ).strip() or _FALLBACK_TZ


def now_local() -> datetime:
    """Current time in EVI_TIMEZONE.

    The container clock is UTC; a naive datetime.now() put the agent a day ahead
    every evening in America/Sao_Paulo.
    """
    try:
        return datetime.now(ZoneInfo(evi_timezone()))
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(ZoneInfo(_FALLBACK_TZ))


def normalize_wall_clock(iso_time: str) -> str:
    """Strip UTC/offset suffix; keep YYYY-MM-DDTHH:MM:SS local wall clock."""
    t = (iso_time or "").strip()
    t = _OFFSET_SUFFIX.sub("", t)
    if len(t) == 16 and t[10] == "T":
        t += ":00"
    return t


def iso_event_range(event_date: str | None, event_time: str | None) -> tuple[str, str]:
    """Return local start/end ISO strings (1h duration) for a pending event row."""
    date = event_date or now_local().strftime("%Y-%m-%d")
    time = event_time or "12:00"
    if len(time) == 5:
        start = datetime.strptime(f"{date}T{time}:00", "%Y-%m-%dT%H:%M:%S")
    else:
        start = datetime.strptime(f"{date}T12:00:00", "%Y-%m-%dT%H:%M:%S")
    end = start + timedelta(hours=1)
    return (
        start.strftime("%Y-%m-%dT%H:%M:%S"),
        end.strftime("%Y-%m-%dT%H:%M:%S"),
    )
