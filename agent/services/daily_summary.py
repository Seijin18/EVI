"""Daily per-contact summaries (Etapa 5a) — filesystem + Postgres context."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from services.contact_filesystem import contact_dir, ensure_contact, list_contact_dirs, memory_enabled


def _today_str(when: date | None = None) -> str:
    return (when or date.today()).strftime("%Y-%m-%d")


def _read_timeline(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _scheduled_today_rows() -> list[dict[str, Any]]:
    if not os.getenv("DATABASE_URL"):
        return []
    try:
        from db import init_db, list_scheduled_today

        init_db()
        return list_scheduled_today(limit=50)
    except Exception:
        return []


def build_summary_markdown(
    jid: str,
    *,
    day: date | None = None,
    label: str = "",
) -> str:
    day_s = _today_str(day)
    root = ensure_contact(jid, label=label)
    timeline = _read_timeline(root / "timeline.jsonl")
    day_entries = [e for e in timeline if str(e.get("ts", "")).startswith(day_s)]
    scheduled = [
        r
        for r in _scheduled_today_rows()
        if (r.get("source_chat") or "") == jid
    ]
    lines = [
        f"# Resumo {day_s}",
        "",
        f"**Contato:** {label or jid}",
        "",
        "## Timeline",
    ]
    if day_entries:
        for e in day_entries:
            lines.append(f"- {e.get('ts', '?')}: {e.get('text_preview', '')}")
    else:
        lines.append("- (sem entradas na timeline hoje)")
    lines.append("")
    lines.append("## Compromissos agendados hoje")
    if scheduled:
        for r in scheduled:
            title = r.get("title") or "(sem título)"
            ctype = r.get("type") or "?"
            lines.append(f"- [{ctype}] {title}")
    else:
        lines.append("- (nenhum)")
    lines.append("")
    return "\n".join(lines)


def write_summary(jid: str, content: str, *, day: date | None = None) -> Path:
    root = ensure_contact(jid)
    out = root / "summaries" / f"{_today_str(day)}.md"
    out.write_text(content, encoding="utf-8")
    return out


def run_daily_summaries(*, day: date | None = None) -> int:
    """Generate summaries for all contact dirs; returns count written."""
    if not memory_enabled():
        return 0
    written = 0
    seen_jids: set[str] = set()
    for path in list_contact_dirs():
        jid = path.name
        seen_jids.add(jid)
        content = build_summary_markdown(jid, day=day)
        write_summary(jid, content, day=day)
        written += 1
    for row in _scheduled_today_rows():
        jid = row.get("source_chat") or ""
        if not jid or jid in seen_jids:
            continue
        label = row.get("source_label") or ""
        content = build_summary_markdown(jid, day=day, label=label)
        write_summary(jid, content, day=day)
        written += 1
        seen_jids.add(jid)
    return written
