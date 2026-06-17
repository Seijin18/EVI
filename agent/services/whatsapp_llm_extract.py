"""Optional Ollama fallback when heuristic WhatsApp extraction returns None."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Callable, Optional

from services.commitment_priority import classify_priority
from services.message_sources import IncomingMessage
from services.whatsapp_processor import Commitment, _parse_ref_dt

_PROMPT = """Extract a calendar commitment from this WhatsApp message (Brazilian Portuguese).
Reference date (message sent): {ref_date}
Contact context:
{contact_context}
Message: {text}

If there is NO schedulable commitment (casual chat, acknowledgements, vague mentions), reply exactly: {{"none": true}}
Otherwise reply ONLY valid JSON with keys:
type ("event" or "task"), title (short, descriptive — not generic like "Item" or "Reunião"), date (YYYY-MM-DD or null), time (HH:MM or null), due (YYYY-MM-DD or null), confidence (0.0-1.0)
Use the reference date to resolve relative days like "dia 12" (day of month in same month/year).
Ignore group banter without a concrete schedule.
"""


def llm_extract_enabled() -> bool:
    return os.getenv("EVI_WHATSAPP_LLM_EXTRACT", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def _min_confidence() -> float:
    try:
        return float(os.getenv("EVI_WHATSAPP_LLM_MIN_CONFIDENCE", "0.6"))
    except ValueError:
        return 0.6


def _timeout_sec() -> int:
    try:
        return int(os.getenv("EVI_WHATSAPP_LLM_TIMEOUT_SEC", "30"))
    except ValueError:
        return 30


def _extract_json_blob(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _resolve_day_of_month(ref: datetime, day: int) -> str:
    candidate = ref.replace(day=day)
    if candidate.date() < ref.date():
        if ref.month == 12:
            candidate = candidate.replace(year=ref.year + 1, month=1)
        else:
            candidate = candidate.replace(month=ref.month + 1)
    return candidate.strftime("%Y-%m-%d")


def _normalize_llm_fields(
    data: dict[str, Any], msg: IncomingMessage
) -> Optional[Commitment]:
    if data.get("none") is True:
        return None

    ctype = str(data.get("type") or "").strip().lower()
    if ctype not in ("event", "task"):
        return None

    title = str(data.get("title") or "").strip()
    if len(title) < 3 or title.lower() in ("reunião", "reuniao", "item", "meeting", "event", "arrival"):
        return None

    try:
        confidence = float(data.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    if confidence < _min_confidence():
        return None

    date_str = data.get("date") or None
    time_str = data.get("time") or None
    due_str = data.get("due") or None

    if date_str:
        date_str = str(date_str)[:10]
    if time_str:
        time_str = str(time_str)[:5]
    if due_str:
        due_str = str(due_str)[:10]

    ref = _parse_ref_dt(msg.ts)
    day_m = re.search(r"\bdia\s+(\d{1,2})\b", msg.text, re.I)
    if day_m and not date_str and not due_str:
        date_str = _resolve_day_of_month(ref, int(day_m.group(1)))

    tm = re.search(r"(\d{1,2})[h:](\d{2})?", msg.text, re.I)
    if tm and not time_str:
        h, m = int(tm.group(1)), int(tm.group(2) or 0)
        time_str = f"{h:02d}:{m:02d}"

    return Commitment(
        source_id=msg.id,
        type=ctype,
        title=title[:80],
        date=date_str,
        time=time_str,
        due=due_str or (date_str if ctype == "task" and date_str else None),
        confidence=confidence,
        priority=classify_priority(msg.text),
    )


def _default_invoke(prompt: str) -> str:
    from llm import build_llm, extract_llm_text

    llm = build_llm(temperature=0.0, num_ctx=2048)
    response = llm.invoke(prompt)
    if hasattr(response, "content"):
        return extract_llm_text(response.content)
    return str(response)


def _contact_context(msg: IncomingMessage) -> str:
    try:
        from services.contact_filesystem import read_profile_excerpt, read_timeline_tail

        jid = msg.sender or ""
        parts: list[str] = []
        profile = read_profile_excerpt(jid)
        if profile:
            parts.append(f"Profile:\n{profile}")
        timeline = read_timeline_tail(jid, limit=3)
        if timeline:
            previews = [e.get("text_preview", "") for e in timeline if e.get("text_preview")]
            if previews:
                parts.append("Recent timeline:\n" + "\n".join(f"- {p}" for p in previews))
        return "\n".join(parts) if parts else "(no contact memory)"
    except Exception:
        return "(no contact memory)"


def try_llm_extract(
    msg: IncomingMessage,
    invoke: Callable[[str], str] | None = None,
) -> Optional[Commitment]:
    """Attempt structured LLM extraction. Returns None on disable, parse error, or low confidence."""
    if not llm_extract_enabled():
        return None

    ref = _parse_ref_dt(msg.ts)
    prompt = _PROMPT.format(
        ref_date=ref.strftime("%Y-%m-%d"),
        contact_context=_contact_context(msg),
        text=msg.text.strip(),
    )
    try:
        raw = (invoke or _default_invoke)(prompt)
    except Exception:
        return None

    data = _extract_json_blob(raw)
    if not data:
        return None
    return _normalize_llm_fields(data, msg)


def extract_commitment_with_fallback(
    msg: IncomingMessage,
    invoke: Callable[[str], str] | None = None,
) -> tuple[Optional[Commitment], str]:
    """
    Run heuristic first, then optional LLM.
    Returns (commitment, method) where method is heuristic|llm|none.
    """
    from services.whatsapp_processor import extract_commitment

    c = extract_commitment(msg)
    if c:
        return c, "heuristic"

    c = try_llm_extract(msg, invoke=invoke)
    if c:
        return c, "llm"
    return None, "none"
