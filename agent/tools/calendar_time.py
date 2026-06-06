"""Calendar datetime helpers — local wall clock + IANA timezone for Google API."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

_OFFSET_SUFFIX = re.compile(r"([+-]\d{2}:\d{2}|Z)$")


def evi_timezone() -> str:
    return os.getenv("EVI_TIMEZONE", "America/Sao_Paulo").strip() or "America/Sao_Paulo"


def normalize_wall_clock(iso_time: str) -> str:
    """Strip UTC/offset suffix; keep YYYY-MM-DDTHH:MM:SS local wall clock."""
    t = (iso_time or "").strip()
    t = _OFFSET_SUFFIX.sub("", t)
    if len(t) == 16 and t[10] == "T":
        t += ":00"
    return t


def iso_event_range(event_date: str | None, event_time: str | None) -> tuple[str, str]:
    """Return local start/end ISO strings (1h duration) for a pending event row."""
    date = event_date or datetime.now().strftime("%Y-%m-%d")
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
