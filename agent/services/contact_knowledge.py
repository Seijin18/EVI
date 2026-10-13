"""Structured per-contact knowledge inside profile.md (facts / open items / notes).

Pure file logic: parsing, rendering, capped replacement of `## Fatos` and
`## Em aberto`, and a metadata-free read for LLM consumers. The user's
`## Notas` section and any other section (legacy `## Síntese (...)`) are
preserved verbatim; the EVI never writes to Notas.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MAX_FACTS = 15
MAX_OPEN_ITEMS = 5
NOTES_PLACEHOLDER = "(livre, do usuário; o EVI nunca escreve aqui)"

_H_FACTS = "Fatos"
_H_OPEN = "Em aberto"
_H_NOTES = "Notas"

_ITEM_RE = re.compile(r"^-\s+(.*?)\s*\((\d{4}-\d{2}-\d{2})\)\s*$")
_BULLET_RE = re.compile(r"^-\s+(.*\S)\s*$")
_META_RE = re.compile(r"^- \*\*[\w-]+\*\*:")
_UPDATED_RE = re.compile(r"^-\s*\*\*knowledge_updated\*\*:\s*(.*?)\s*$")


@dataclass
class Fact:
    text: str
    date: str | None = None  # YYYY-MM-DD


@dataclass
class Item:
    text: str
    date: str | None = None  # YYYY-MM-DD


@dataclass
class Profile:
    header: str = ""
    facts: list[Fact] = field(default_factory=list)
    open_items: list[Item] = field(default_factory=list)
    notes: str = NOTES_PLACEHOLDER
    other_sections: list[tuple[str, str]] = field(default_factory=list)
    knowledge_updated: datetime | None = None


def _parse_entry(line: str, cls):
    stripped = line.strip()
    m = _ITEM_RE.match(stripped)
    if m and m.group(1):
        return cls(m.group(1), m.group(2))
    m = _BULLET_RE.match(stripped)
    if m:
        return cls(m.group(1), None)
    return None


def _parse_dt(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_profile(text: str) -> Profile:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    header_lines: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            header_lines.append(line)

    profile = Profile(notes="")
    kept: list[str] = []
    for line in header_lines:
        m = _UPDATED_RE.match(line.strip())
        if m and profile.knowledge_updated is None:
            profile.knowledge_updated = _parse_dt(m.group(1))
            if profile.knowledge_updated is not None:
                continue
        kept.append(line)
    profile.header = "\n".join(kept).strip("\n")

    notes_seen = False
    for heading, body_lines in sections:
        body = "\n".join(body_lines).rstrip("\n")
        if heading == _H_FACTS:
            for ln in body_lines:
                entry = _parse_entry(ln, Fact)
                if entry:
                    profile.facts.append(entry)
        elif heading == _H_OPEN:
            for ln in body_lines:
                entry = _parse_entry(ln, Item)
                if entry:
                    profile.open_items.append(entry)
        elif heading == _H_NOTES and not notes_seen:
            notes_seen = True
            profile.notes = body.lstrip("\n")
        else:
            profile.other_sections.append((heading, body))
    if not profile.notes.strip():
        profile.notes = NOTES_PLACEHOLDER
    return profile


def _entry_line(e: Fact | Item) -> str:
    return f"- {e.text} ({e.date})" if e.date else f"- {e.text}"


def _render_header(profile: Profile) -> str:
    lines = profile.header.split("\n") if profile.header else []
    if profile.knowledge_updated is not None:
        line = f"- **knowledge_updated**: {profile.knowledge_updated.isoformat()}"
        idx = max((i for i, ln in enumerate(lines) if _META_RE.match(ln)), default=-1)
        if idx >= 0:
            lines.insert(idx + 1, line)
        else:
            lines.extend(["", line] if lines else [line])
    return "\n".join(lines)


def render_profile(profile: Profile) -> str:
    blocks: list[str] = []
    header = _render_header(profile)
    if header.strip():
        blocks.append(header)
    facts = "\n".join(_entry_line(f) for f in profile.facts)
    blocks.append(f"## {_H_FACTS}\n{facts}" if facts else f"## {_H_FACTS}")
    items = "\n".join(_entry_line(i) for i in profile.open_items)
    blocks.append(f"## {_H_OPEN}\n{items}" if items else f"## {_H_OPEN}")
    notes = profile.notes if profile.notes.strip() else NOTES_PLACEHOLDER
    blocks.append(f"## {_H_NOTES}\n{notes}")
    for heading, body in profile.other_sections:
        blocks.append(f"## {heading}\n{body}" if body else f"## {heading}")
    return "\n\n".join(blocks) + "\n"


def _cap(entries: list, limit: int) -> list:
    """Keep the `limit` most recent by date (undated = oldest), original order."""
    if len(entries) <= limit:
        return list(entries)
    ranked = sorted(range(len(entries)), key=lambda i: (entries[i].date or "", i), reverse=True)
    keep = sorted(ranked[:limit])
    return [entries[i] for i in keep]


def _coerce(entries, cls) -> list:
    out = []
    for e in entries or []:
        if isinstance(e, cls):
            text, date = e.text, e.date
        elif isinstance(e, (tuple, list)):
            text, date = e[0], (e[1] if len(e) > 1 else None)
        elif isinstance(e, dict):
            text, date = e.get("text", ""), e.get("date")
        else:
            text, date = str(e), None
        text = " ".join(str(text or "").split())
        if not text:
            continue
        date = str(date) if date else None
        out.append(cls(text, date))
    return out


def _profile_path(jid: str) -> Path | None:
    from services import contact_filesystem as cf

    if not cf.memory_enabled() or not jid:
        return None
    return cf.contact_dir(jid) / "profile.md"


def _atomic_write(path: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".profile.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_knowledge(
    jid: str,
    facts,
    open_items,
    *,
    updated_at: datetime | None = None,
) -> Path | None:
    """Replace only `## Fatos` / `## Em aberto` (capped) and stamp knowledge_updated."""
    from services import contact_filesystem as cf

    if not cf.memory_enabled() or not jid:
        return None
    if cf.ensure_contact(jid) is None:  # refused (non-direct jid)
        return None
    path = cf.contact_dir(jid) / "profile.md"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    profile = parse_profile(existing)
    profile.facts = _cap(_coerce(facts, Fact), MAX_FACTS)
    profile.open_items = _cap(_coerce(open_items, Item), MAX_OPEN_ITEMS)
    profile.knowledge_updated = updated_at or datetime.now(timezone.utc)
    _atomic_write(path, render_profile(profile))
    return path


def read_knowledge(jid: str) -> Profile | None:
    path = _profile_path(jid)
    if path is None or not path.is_file():
        return None
    try:
        return parse_profile(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def numbered(profile: Profile) -> tuple[list[tuple[str, str, str | None]], list[tuple[str, str, str | None]]]:
    facts = [(f"F{i}", f.text, f.date) for i, f in enumerate(profile.facts, 1)]
    items = [(f"A{i}", it.text, it.date) for i, it in enumerate(profile.open_items, 1)]
    return facts, items


def read_contact_knowledge(jid: str, max_chars: int = 1200) -> str:
    """Facts, open items and user notes, without header metadata, within max_chars."""
    profile = read_knowledge(jid)
    if profile is None:
        return ""
    notes = ""
    if profile.notes.strip() and profile.notes.strip() != NOTES_PLACEHOLDER:
        notes = profile.notes
    parts = [
        ("Fatos:", [_entry_line(f) for f in profile.facts]),
        ("Em aberto:", [_entry_line(i) for i in profile.open_items]),
        ("Notas:", [ln for ln in notes.split("\n") if ln.strip()]),
    ]
    out: list[str] = []
    size = 0
    full = True
    for label, body in parts:
        if not body or not full:
            continue
        chosen: list[str] = []
        added = len(label) + (1 if out else 0)
        for ln in body:
            cost = len(ln) + 1
            if size + added + cost > max_chars:
                full = False
                break
            chosen.append(ln)
            added += cost
        if chosen:
            out.append(label)
            out.extend(chosen)
            size += added
    return "\n".join(out)
