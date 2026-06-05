"""Direct Calendar scheduling for Telegram when the LLM skips tool calls."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from tools.calendar_time import evi_timezone

_INTENT = re.compile(
    r"\b(agende|agendar|crie?\s+um?\s+evento|criar\s+evento|marque|marcar)\b",
    re.I,
)
_QUOTE_CHARS = "\"'\u201c\u201d\u201e\u201a«»"
_QUOTED = re.compile(
    rf"[{re.escape(_QUOTE_CHARS)}]([^{re.escape(_QUOTE_CHARS)}]+)[{re.escape(_QUOTE_CHARS)}]"
)
_TIME = re.compile(
    r"(?:às|as|para\s+as?)\s*(\d{1,2})(?::(\d{2}))?\s*h?",
    re.I,
)
_TITLE_HINT = re.compile(
    rf"(?:nome|chamad[oa]|titulo|título)\s+[{re.escape(_QUOTE_CHARS)}]?([^{re.escape(_QUOTE_CHARS)}\n,.]+)",
    re.I,
)


def _now_local() -> datetime:
    return datetime.now(ZoneInfo(evi_timezone()))


def _parse_when(text: str) -> Tuple[str, str, str]:
    """Return (date YYYY-MM-DD, start HH:MM, end HH:MM) in local wall clock."""
    low = text.lower()
    now = _now_local()
    if "amanhã" in low or "amanha" in low:
        day = (now + timedelta(days=1)).date()
    else:
        day = now.date()

    hour, minute = 12, 0
    m = _TIME.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)

    start = datetime.combine(day, datetime.min.time()).replace(
        hour=hour, minute=minute
    )
    end = start + timedelta(hours=1)
    return (
        day.isoformat(),
        start.strftime("%H:%M"),
        end.strftime("%H:%M"),
    )


def _strip_quotes(s: str) -> str:
    return s.strip().strip(_QUOTE_CHARS)


def _parse_title(text: str) -> str:
    for pat in (_QUOTED, _TITLE_HINT):
        m = pat.search(text)
        if m:
            title = _strip_quotes(m.group(1))
            if title:
                return title[:120]
    low = text.lower()
    for word in ("almoço", "almoco", "café da manhã", "cafe da manha", "jantar"):
        if word in low:
            return word
    return "Compromisso EVI"


def wants_schedule(text: str) -> bool:
    return bool(_INTENT.search(text))


def try_direct_schedule(text: str) -> Optional[str]:
    """Call schedule_event when user clearly asks to book; None if not applicable."""
    if not wants_schedule(text):
        return None

    date_s, start_hm, end_hm = _parse_when(text)
    title = _parse_title(text)
    start_time = f"{date_s}T{start_hm}:00" if len(start_hm) == 5 else f"{date_s}T{start_hm}"
    end_time = f"{date_s}T{end_hm}:00" if len(end_hm) == 5 else f"{date_s}T{end_hm}"

    from tools.calendar_tool import schedule_event

    return schedule_event.invoke(
        {
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "description": "Criado via Telegram (EVI direct schedule)",
        }
    )
