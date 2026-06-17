"""Extract commitments (events/tasks) from chat messages — deterministic Tier 2."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.commitment_priority import classify_priority
from services.message_sources import IncomingMessage, load_messages


@dataclass
class Commitment:
    source_id: str
    type: str  # event | task
    title: str
    date: Optional[str] = None
    time: Optional[str] = None
    due: Optional[str] = None
    confidence: float = 0.75
    priority: str = "normal"

    def to_golden_row(self) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "source_id": self.source_id,
            "type": self.type,
            "title": self.title,
        }
        if self.date:
            row["date"] = self.date
        if self.time:
            row["time"] = self.time
        if self.due:
            row["due"] = self.due
        if self.priority != "normal":
            row["priority"] = self.priority
        return row


# Skip acknowledgements and very short noise
_SKIP_PATTERNS = re.compile(
    r"^(ok|okay|combinado|valeu|obrigad|👍|sim|não)\b", re.I
)

_TIME_RE = re.compile(r"(\d{1,2})[h:](\d{2})?", re.I)
_REL_DAY_RE = re.compile(r"\bamanh[ãa]\b", re.I)
_TODAY_RE = re.compile(r"\bhoje\b", re.I)
_FRIDAY_RE = re.compile(r"\bsexta(?:-feira)?\b", re.I)
_SUNDAY_RE = re.compile(r"\bdomingo\b", re.I)
_MEETING_RE = re.compile(r"\b(reuni[ãa]o|encontro|call)\b", re.I)
_REMIND_RE = re.compile(r"\b(lembre|enviar|mandar|entregar|relat[oó]rio)\b", re.I)
_DINNER_RE = re.compile(r"\b(jantar|almoco|almoço)\b", re.I)
_NEXT_WEEK_RE = re.compile(r"\bpr[oó]xima?\s+semana\b", re.I)
_WEEKDAY_RE = re.compile(
    r"\b(segunda(?:-feira)?|ter[cç]a(?:-feira)?|quarta(?:-feira)?|quinta(?:-feira)?|"
    r"s[aá]bado)\b",
    re.I,
)
_WEEKDAY_MAP = {
    "segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3, "sábado": 5, "sabado": 5,
}
_MONTH_DAY_RE = re.compile(
    r"\b(?:dia\s+)?(\d{1,2})\s+de\s+"
    r"(jan(?:eiro)?|fev(?:ereiro)?|mar(?:ço|co)?|abr(?:il)?|mai(?:o)?|jun(?:ho)?|"
    r"jul(?:ho)?|ago(?:sto)?|set(?:embro)?|out(?:ubro)?|nov(?:embro)?|dez(?:embro)?)\b",
    re.I,
)
_MONTH_MAP = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}
_PERIOD_RE = re.compile(r"\b(de\s+manh[ãa]|[àa]\s+tarde|[àa]\s+noite|[àa]\s+meia[\s-]noite)\b", re.I)
_PERIOD_TIME = {"manhã": "09:00", "manha": "09:00", "tarde": "14:00", "noite": "20:00", "meia": "00:00"}


def _parse_ref_dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00").split("+")[0])


def _next_weekday(ref: datetime, weekday: int) -> datetime:
    """weekday: Monday=0 .. Sunday=6"""
    days_ahead = (weekday - ref.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return ref + timedelta(days=days_ahead)


def _resolve_date(text: str, ref: datetime) -> Optional[str]:
    """Return ISO date string from natural language date expressions, or None."""
    if _TODAY_RE.search(text):
        return ref.strftime("%Y-%m-%d")
    if _REL_DAY_RE.search(text):
        return (ref + timedelta(days=1)).strftime("%Y-%m-%d")
    if _NEXT_WEEK_RE.search(text):
        return _next_weekday(ref, 0).strftime("%Y-%m-%d")
    m = _MONTH_DAY_RE.search(text)
    if m:
        day = int(m.group(1))
        mon_key = m.group(2)[:3].lower()
        month = _MONTH_MAP.get(mon_key)
        if month:
            year = ref.year if month >= ref.month else ref.year + 1
            try:
                from datetime import date as _date
                return _date(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                pass
    m = _WEEKDAY_RE.search(text)
    if m:
        key = m.group(1).lower().rstrip("-feira").replace("ç", "c").replace("á", "a").replace("ã", "a")
        key = re.sub(r"-feira$", "", key)
        for wk, idx in _WEEKDAY_MAP.items():
            if key.startswith(wk[:4]):
                return _next_weekday(ref, idx).strftime("%Y-%m-%d")
    if _FRIDAY_RE.search(text):
        return _next_weekday(ref, 4).strftime("%Y-%m-%d")
    if _SUNDAY_RE.search(text):
        return _next_weekday(ref, 6).strftime("%Y-%m-%d")
    return None


def _resolve_time(text: str) -> Optional[str]:
    """Return HH:MM from explicit time or period-of-day, or None."""
    m = _TIME_RE.search(text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2) or 0)
        return f"{h:02d}:{mn:02d}"
    pm = _PERIOD_RE.search(text)
    if pm:
        word = pm.group(1).lower()
        for key, val in _PERIOD_TIME.items():
            if key in word:
                return val
    return None


_GENERIC_TITLES = frozenset({"reunião", "reuniao", "item", "reunião", "meeting", "event"})


def _is_generic_title(title: str) -> bool:
    t = title.strip().lower()
    return t in _GENERIC_TITLES or len(t) < 4


def extract_commitment(msg: IncomingMessage) -> Optional[Commitment]:
    text = msg.text.strip()
    if len(text) < 12 or _SKIP_PATTERNS.match(text):
        return None

    ref = _parse_ref_dt(msg.ts)
    date_str: Optional[str] = _resolve_date(text, ref)
    time_str: Optional[str] = _resolve_time(text)
    due_str: Optional[str] = None
    ctype = "task"
    title = text[:80]

    if _MEETING_RE.search(text):
        ctype = "event"
        m = re.search(r"reuni[ãa]o\s+com\s+([^,.]+)", text, re.I)
        if m:
            title = f"Reunião com {m.group(1).strip()}".capitalize()[:60]
        elif not (date_str or time_str):
            return None
        else:
            title = "Reunião"
    elif _REMIND_RE.search(text):
        ctype = "task"
        m = re.search(r"(enviar|mandar|entregar)\s+(.+?)(?:\s+até|\s+ate|$)", text, re.I)
        if m:
            title = (m.group(1) + " " + m.group(2)).strip().capitalize()[:60]
        elif "relat" in text.lower():
            title = "Enviar relatório"
    elif _DINNER_RE.search(text):
        ctype = "event"
        title = "Jantar"
        if not date_str and _SUNDAY_RE.search(text):
            date_str = _next_weekday(ref, 6).strftime("%Y-%m-%d")

    if not (_MEETING_RE.search(text) or _REMIND_RE.search(text) or _DINNER_RE.search(text)):
        return None

    if _is_generic_title(title):
        return None

    return Commitment(
        source_id=msg.id,
        type=ctype,
        title=title,
        date=date_str,
        time=time_str,
        due=due_str or (date_str if ctype == "task" and date_str else None),
        confidence=0.8 if ctype == "event" else 0.7,
        priority=classify_priority(text),
    )


class WhatsAppProcessor:
    def __init__(self, log_path: Path | None = None, verbose: bool = False):
        self.log_path = log_path
        self.verbose = verbose
        self._log_entries: List[Dict[str, Any]] = []

    def log(self, entry: Dict[str, Any]) -> None:
        if "ts" not in entry:
            entry = {
                **entry,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        self._log_entries.append(entry)
        if self.verbose:
            print(json.dumps(entry, ensure_ascii=False))

    def flush_log(self) -> None:
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                for e in self._log_entries:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            self._log_entries.clear()

    def process_messages(self, messages: List[IncomingMessage]) -> List[Commitment]:
        seen: set[str] = set()
        results: List[Commitment] = []
        for msg in messages:
            preview = msg.text[:80] + ("..." if len(msg.text) > 80 else "")
            self.log(
                {
                    "step": "ingest",
                    "message_ts": msg.ts or "",
                    "source_id": msg.id,
                    "sender": msg.sender,
                    "from_me": msg.from_me,
                    "is_group": msg.is_group,
                    "raw_preview": preview,
                }
            )

            from services.whatsapp_llm_extract import extract_commitment_with_fallback

            c, method = extract_commitment_with_fallback(msg)
            if c and c.source_id not in seen:
                seen.add(c.source_id)
                results.append(c)
                self.log(
                    {
                        "step": "extract",
                        "source_id": msg.id,
                        "method": method,
                        "commitments": [c.to_golden_row()],
                    }
                )
            elif method == "none":
                from services.whatsapp_llm_extract import llm_extract_enabled

                if llm_extract_enabled():
                    self.log(
                        {
                            "step": "llm_extract_skip",
                            "source_id": msg.id,
                        }
                    )
        self.log({"step": "dedupe", "merged": len(messages) - len(results)})
        return results

    def compare_golden(
        self, extracted: List[Commitment], golden_path: Path
    ) -> bool:
        with golden_path.open(encoding="utf-8") as f:
            golden = json.load(f)

        matched = 0
        for g in golden:
            gid = g["source_id"]
            found = next((e for e in extracted if e.source_id == gid), None)
            if not found:
                self.log(
                    {
                        "step": "compare_golden",
                        "pass": False,
                        "source_id": gid,
                        "reason": "missing",
                    }
                )
                continue
            ok = found.type == g["type"]
            if g.get("title"):
                exp = g["title"].lower().replace(" o ", " ")
                got = found.title.lower().replace(" o ", " ")
                ok = ok and (exp in got or got in exp or exp.split()[-1] in got)
            if g.get("date"):
                ok = ok and found.date == g["date"]
            if g.get("time"):
                ok = ok and found.time == g["time"]
            if g.get("due"):
                ok = ok and (found.due == g["due"] or found.date == g["due"])
            if ok:
                matched += 1
            self.log(
                {
                    "step": "compare_golden",
                    "pass": ok,
                    "source_id": gid,
                    "expected": 1,
                    "got": 1 if ok else 0,
                }
            )

        overall = matched == len(golden)
        self.log(
            {
                "step": "compare_golden_summary",
                "pass": overall,
                "expected": len(golden),
                "got": matched,
            }
        )
        return overall


def process_fixture_file(
    fixture_path: Path,
    golden_path: Path,
    log_path: Path | None = None,
    verbose: bool = False,
) -> bool:
    messages = load_messages("fixture", fixture_path)
    proc = WhatsAppProcessor(log_path=log_path, verbose=verbose)
    extracted = proc.process_messages(messages)
    ok = proc.compare_golden(extracted, golden_path)
    proc.flush_log()
    return ok

