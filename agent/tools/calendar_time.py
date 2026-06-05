"""Calendar datetime helpers — local wall clock + IANA timezone for Google API."""

from __future__ import annotations

import os
import re

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
