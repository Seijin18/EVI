"""Daily per-contact summaries (Etapa 5a) — filesystem + Postgres context."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from services.contact_filesystem import ensure_contact, list_contact_dirs, memory_enabled


def _today_str(when: date | None = None) -> str:
    if when:
        return when.strftime("%Y-%m-%d")
    tz = ZoneInfo(os.getenv("EVI_TIMEZONE", "America/Sao_Paulo"))
    return datetime.now(tz).date().strftime("%Y-%m-%d")


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


def _llm_summarize(raw_md: str) -> str:
    from llm import build_llm, extract_llm_text

    prompt = f"Gere um resumo diário conciso em português a partir deste contexto:\n\n{raw_md}"
    try:
        resp = build_llm(temperature=0.3).invoke(prompt)
        if hasattr(resp, "content"):
            return extract_llm_text(resp.content)
        return str(resp)
    except Exception:
        return raw_md


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
    raw = "\n".join(lines)
    if os.getenv("EVI_DAILY_SUMMARY_LLM", "").lower() in ("1", "true", "yes"):
        return _llm_summarize(raw)
    return raw


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


def heartbeat_enabled() -> bool:
    return os.getenv("EVI_HEARTBEAT_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def read_heartbeat_checklist() -> str:
    from services.workspace import read_bootstrap_file

    return read_bootstrap_file("HEARTBEAT.md")


def run_heartbeat_dry() -> dict[str, Any]:
    """Return checklist + pending count without sending messages (cron stub)."""
    out: dict[str, Any] = {"ok": True, "enabled": heartbeat_enabled()}
    out["checklist"] = read_heartbeat_checklist()
    try:
        from db import count_unnotified_pending, init_db

        init_db()
        out["pending_unnotified"] = count_unnotified_pending()
    except Exception:
        out["pending_unnotified"] = 0
    return out
