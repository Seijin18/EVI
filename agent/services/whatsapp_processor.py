"""Extract commitments (events/tasks) from chat messages — deterministic Tier 2."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
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
_FRIDAY_RE = re.compile(r"\bsexta\b", re.I)
_SUNDAY_RE = re.compile(r"\bdomingo\b", re.I)
_MEETING_RE = re.compile(r"\b(reuni[ãa]o|encontro|call)\b", re.I)
_REMIND_RE = re.compile(r"\b(lembre|enviar|mandar|entregar|relat[oó]rio)\b", re.I)
_DINNER_RE = re.compile(r"\b(jantar|almoco|almoço)\b", re.I)


def _parse_ref_dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00").split("+")[0])


def _next_weekday(ref: datetime, weekday: int) -> datetime:
    """weekday: Monday=0 .. Sunday=6"""
    days_ahead = (weekday - ref.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return ref + timedelta(days=days_ahead)


def extract_commitment(msg: IncomingMessage) -> Optional[Commitment]:
    text = msg.text.strip()
    if len(text) < 12 or _SKIP_PATTERNS.match(text):
        return None

    ref = _parse_ref_dt(msg.ts)
    date_str: Optional[str] = None
    time_str: Optional[str] = None
    due_str: Optional[str] = None
    ctype = "task"
    title = text[:80]

    if _REL_DAY_RE.search(text):
        date_str = (ref + timedelta(days=1)).strftime("%Y-%m-%d")
    elif _FRIDAY_RE.search(text):
        due_str = _next_weekday(ref, 4).strftime("%Y-%m-%d")
    elif _SUNDAY_RE.search(text):
        date_str = _next_weekday(ref, 6).strftime("%Y-%m-%d")

    tm = _TIME_RE.search(text)
    if tm:
        h, m = int(tm.group(1)), int(tm.group(2) or 0)
        time_str = f"{h:02d}:{m:02d}"

    if _MEETING_RE.search(text):
        ctype = "event"
        m = re.search(r"reuni[ãa]o\s+com\s+([^,.]+)", text, re.I)
        if m:
            title = f"Reunião com {m.group(1).strip()}".capitalize()[:60]
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
            preview = msg.text[:50] + ("..." if len(msg.text) > 50 else "")
            self.log({"step": "ingest", "source_id": msg.id, "raw_preview": preview})

            c = extract_commitment(msg)
            if c and c.source_id not in seen:
                seen.add(c.source_id)
                results.append(c)
                self.log(
                    {
                        "step": "extract",
                        "source_id": msg.id,
                        "commitments": [c.to_golden_row()],
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

