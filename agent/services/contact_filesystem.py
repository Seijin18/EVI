"""Cold per-contact filesystem memory (Etapa 5a)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_JID_SAFE = re.compile(r"[^a-zA-Z0-9@._-]+")
_PROFILE_TEMPLATE = """# Contact memory

- **jid**: {jid}
- **label**: {label}
- **created**: {created}

Stable facts and preferences go here (manual or future LLM enrichment).
"""


def memory_enabled() -> bool:
    return bool(os.getenv("EVI_CONTACT_MEMORY_DIR", "").strip())


def memory_root() -> Path:
    raw = os.getenv("EVI_CONTACT_MEMORY_DIR", "").strip()
    if not raw:
        raise RuntimeError("EVI_CONTACT_MEMORY_DIR not set")
    return Path(raw)


def sanitize_jid(jid: str) -> str:
    cleaned = _JID_SAFE.sub("_", (jid or "unknown").strip())
    return cleaned[:120] or "unknown"


def contact_dir(jid: str) -> Path:
    return memory_root() / "contacts" / sanitize_jid(jid)


def ensure_contact(jid: str, *, label: str = "") -> Path:
    root = contact_dir(jid)
    root.mkdir(parents=True, exist_ok=True)
    (root / "summaries").mkdir(exist_ok=True)
    profile = root / "profile.md"
    if not profile.exists():
        profile.write_text(
            _PROFILE_TEMPLATE.format(
                jid=jid,
                label=label or jid,
                created=datetime.now(timezone.utc).isoformat(),
            ),
            encoding="utf-8",
        )
    timeline = root / "timeline.jsonl"
    if not timeline.exists():
        timeline.touch()
    return root


def append_timeline(
    jid: str,
    *,
    source_id: str,
    text_preview: str,
    commitment_id: int | None = None,
    label: str = "",
    ts: str | None = None,
    backfill: bool = False,
) -> bool:
    if not memory_enabled() or not jid:
        return False
    ensure_contact(jid, label=label)
    entry: dict[str, Any] = {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "text_preview": (text_preview or "")[:500],
    }
    if commitment_id is not None:
        entry["commitment_id"] = commitment_id
    if backfill:
        entry["backfill"] = True
    path = contact_dir(jid) / "timeline.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True


def timeline_source_ids(jid: str) -> set[str]:
    if not memory_enabled() or not jid:
        return set()
    path = contact_dir(jid) / "timeline.jsonl"
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = row.get("source_id")
        if sid:
            ids.add(str(sid))
    return ids


def ingest_commitment(
    *,
    jid: str,
    source_id: str,
    title: str,
    raw_text: str,
    commitment_id: int,
    label: str = "",
) -> bool:
    """Write timeline entry after a commitment is queued."""
    preview = f"{title}: {(raw_text or '')[:200]}".strip()
    return append_timeline(
        jid,
        source_id=source_id,
        text_preview=preview,
        commitment_id=commitment_id,
        label=label,
    )


def list_contact_dirs() -> list[Path]:
    if not memory_enabled():
        return []
    base = memory_root() / "contacts"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir())


def read_timeline_tail(jid: str, limit: int = 5) -> list[dict[str, Any]]:
    """Last N timeline entries for LLM extract context."""
    if not memory_enabled() or not jid:
        return []
    path = contact_dir(jid) / "timeline.jsonl"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    entries: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def read_timeline_since(jid: str, *, days: int = 30, limit: int = 100) -> list[dict[str, Any]]:
    """Timeline entries from the last N days (newest last)."""
    if not memory_enabled() or not jid or days < 1:
        return []
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    path = contact_dir(jid) / "timeline.jsonl"
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_raw = row.get("ts") or ""
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts >= cutoff:
            entries.append(row)
    return entries[-limit:]


def read_summaries_since(jid: str, *, days: int = 30) -> list[tuple[str, str]]:
    """Daily summary files (date, content) within the last N days."""
    if not memory_enabled() or not jid or days < 1:
        return []
    from datetime import date, datetime, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(os.getenv("EVI_TIMEZONE", "America/Sao_Paulo"))
    today = datetime.now(tz).date()
    cutoff = today - timedelta(days=days)
    summaries_dir = contact_dir(jid) / "summaries"
    if not summaries_dir.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for path in sorted(summaries_dir.glob("*.md")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day >= cutoff:
            out.append((path.stem, path.read_text(encoding="utf-8").strip()[:3000]))
    return out


def append_profile_section(jid: str, *, heading: str, body: str, label: str = "") -> bool:
    """Replace or append a markdown section under heading in profile.md."""
    if not memory_enabled() or not jid or not body.strip():
        return False
    ensure_contact(jid, label=label)
    profile = contact_dir(jid) / "profile.md"
    existing = profile.read_text(encoding="utf-8") if profile.is_file() else ""
    marker = f"## {heading}"
    block = f"{marker}\n\n{body.strip()}\n"
    if marker in existing:
        before, _, after = existing.partition(marker)
        after_body = after.split("\n## ", 1)
        tail = f"\n## {after_body[1]}" if len(after_body) > 1 and after_body[1] else ""
        existing = before.rstrip() + "\n\n" + block + tail
    else:
        existing = (existing.rstrip() + "\n\n" + block) if existing.strip() else block
    profile.write_text(existing.strip() + "\n", encoding="utf-8")
    return True


def read_profile_excerpt(jid: str, max_chars: int = 800) -> str:
    if not memory_enabled() or not jid:
        return ""
    profile = contact_dir(jid) / "profile.md"
    if not profile.is_file():
        return ""
    return profile.read_text(encoding="utf-8").strip()[:max_chars]


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def phone_to_jid(phone: str) -> str:
    """Build a WhatsApp JID from a phone number (digits only + @s.whatsapp.net)."""
    digits = _digits_only(phone)
    if len(digits) < 8:
        return ""
    return f"{digits}@s.whatsapp.net"


def _parse_profile(path: Path) -> tuple[str, str]:
    """Return (jid, label) from profile.md; fall back to directory name."""
    jid = path.parent.name
    label = ""
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("- **jid**:"):
                jid = stripped.split(":", 1)[1].strip()
            elif stripped.lower().startswith("- **label**:"):
                label = stripped.split(":", 1)[1].strip()
    return jid, label or jid


def _name_matches(label: str, query: str) -> bool:
    if not label or not query:
        return False
    a = label.casefold().strip()
    b = query.casefold().strip()
    return b in a or a in b


def _jid_matches_digits(jid: str, query_digits: str) -> bool:
    if not query_digits or len(query_digits) < 8:
        return False
    jid_digits = _digits_only(jid.split("@", 1)[0])
    return query_digits in jid_digits or jid_digits.endswith(query_digits)


def collect_known_contacts() -> list[dict[str, Any]]:
    """Merge filesystem contacts with Postgres source_chat/source_label."""
    by_jid: dict[str, dict[str, Any]] = {}

    if memory_enabled():
        for path in list_contact_dirs():
            profile = path / "profile.md"
            jid, label = _parse_profile(profile)
            timeline = path / "timeline.jsonl"
            entries = 0
            if timeline.is_file():
                entries = sum(1 for ln in timeline.read_text(encoding="utf-8").splitlines() if ln.strip())
            by_jid[jid] = {
                "jid": jid,
                "label": label,
                "timeline_entries": entries,
                "has_profile": profile.is_file(),
            }

    try:
        from db import init_db, list_whatsapp_contact_sources

        init_db()
        for row in list_whatsapp_contact_sources(limit=100):
            jid = (row.get("source_chat") or "").strip()
            if not jid:
                continue
            label = (row.get("source_label") or "").strip()
            existing = by_jid.get(jid)
            if existing:
                if label and (not existing.get("label") or existing["label"] == jid):
                    existing["label"] = label
                existing["commitment_count"] = row.get("commitment_count", 0)
            else:
                by_jid[jid] = {
                    "jid": jid,
                    "label": label or jid,
                    "timeline_entries": 0,
                    "has_profile": False,
                    "commitment_count": row.get("commitment_count", 0),
                }
    except Exception:
        pass

    return sorted(by_jid.values(), key=lambda c: (c.get("label") or c["jid"]).casefold())


def resolve_contact_for_query(query: str) -> tuple[tuple[str, str], str] | tuple[None, str]:
    """Resolve (jid, label) from name, phone or known contact. Never requires raw JID from user."""
    q = (query or "").strip()
    if not q:
        return None, "Informe o nome ou telefone do contato."
    matches = search_contacts(q, limit=5)
    if len(matches) > 1:
        names = ", ".join(c.get("label") or "?" for c in matches)
        return None, f"Vários contatos correspondem a «{q}»: {names}. Seja mais específico."
    if len(matches) == 1:
        c = matches[0]
        return (c["jid"], c.get("label") or q), ""
    jid = phone_to_jid(q)
    if jid:
        return (jid, q), ""
    return None, (
        f"Nenhum contato encontrado para «{q}». "
        "Use list_whatsapp_contacts ou informe o telefone com DDD."
    )


def search_contacts(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Find contacts by display name or phone digits (no JID required from user)."""
    q = (query or "").strip()
    if not q:
        return []
    contacts = collect_known_contacts()
    digits = _digits_only(q)
    jid_guess = phone_to_jid(q) if digits else ""

    scored: list[tuple[int, dict[str, Any]]] = []
    for c in contacts:
        label = c.get("label") or ""
        jid = c.get("jid") or ""
        score = 0
        if label.casefold() == q.casefold():
            score = 100
        elif _name_matches(label, q):
            score = 80
        elif jid_guess and jid == jid_guess:
            score = 90
        elif digits and _jid_matches_digits(jid, digits):
            score = 70
        if score:
            scored.append((score, c))

    scored.sort(key=lambda x: (-x[0], (x[1].get("label") or "").casefold()))
    return [c for _, c in scored[:limit]]
