"""Persist ingested WhatsApp messages to contact timeline."""

from __future__ import annotations

from services.contact_filesystem import (
    append_timeline,
    ensure_contact,
    memory_enabled,
    timeline_source_ids,
)
from services.contact_identity import canonical_jid
from services.evolution_client import is_evi_bot_message
from services.message_sources import IncomingMessage


def _preview(msg: IncomingMessage) -> str:
    text = (msg.text or "").strip()
    if msg.from_me:
        return f"[eu] {text[:400]}"
    if msg.is_group:
        who = msg.label or "grupo"
        return f"[{who}] {text[:400]}"
    who = msg.label or "contato"
    return f"[{who}] {text[:400]}"


def record_whatsapp_message(msg: IncomingMessage) -> bool:
    """Append one ingested message to timeline (chat + optional participant contact)."""
    if not memory_enabled() or not msg.text.strip():
        return False
    if is_evi_bot_message(msg.text):
        return False

    chat_jid = canonical_jid(msg.sender)
    existing = timeline_source_ids(chat_jid)
    if msg.id and msg.id in existing:
        recorded = False
    else:
        recorded = append_timeline(
            chat_jid,
            source_id=msg.id or f"msg_{hash(msg.text) & 0xFFFF}",
            text_preview=_preview(msg),
            label=msg.label,
            ts=msg.ts or None,
        )

    if msg.is_group and msg.participant and "@s.whatsapp.net" in msg.participant:
        part_label = msg.label or msg.participant.split("@", 1)[0]
        ensure_contact(msg.participant, label=part_label)
        part_ids = timeline_source_ids(msg.participant)
        part_key = f"{msg.id}:p" if msg.id else f"grp_{hash(msg.text) & 0xFFFF}"
        if part_key not in part_ids:
            append_timeline(
                msg.participant,
                source_id=part_key,
                text_preview=f"[grupo] {_preview(msg)}",
                label=part_label,
                ts=msg.ts or None,
            )
            recorded = True

    return recorded


def record_whatsapp_messages(messages: list[IncomingMessage]) -> int:
    return sum(1 for m in messages if record_whatsapp_message(m))


# --- reading recent rows (local-first WhatsApp listing) ---------------------------------


def _iter_lines_reverse(path, block: int = 65536):
    """Yield the non-empty lines of ``path`` from the last to the first, in chunks."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        tail = b""
        while pos > 0:
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            parts = (f.read(step) + tail).split(b"\n")
            tail = parts[0]
            for raw in reversed(parts[1:]):
                if raw.strip():
                    yield raw.decode("utf-8", errors="replace")
        if tail.strip():
            yield tail.decode("utf-8", errors="replace")


def _recent_entries(path, cutoff) -> list[dict]:
    """Timeline entries with ts >= cutoff, newest first; stops at the first older entry.

    Backfilled rows are appended after newer ones, so an old backfilled row does not end
    the scan.
    """
    import json

    from services.evolution_discovery import _parse_msg_ts

    out: list[dict] = []
    for line in _iter_lines_reverse(path):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_msg_ts(str(row.get("ts") or ""))
        if ts is None:
            continue
        if ts < cutoff:
            if row.get("backfill"):
                continue
            break
        row["_ts_dt"] = ts
        out.append(row)
    return out


def recent_rows(days: int, limit: int, *, covered: set[str] | None = None) -> list[dict]:
    """Recent direct-chat messages from the local timelines, newest first.

    Same row shape as ``evolution_discovery.fetch_recent_whatsapp_messages``. Group
    messages recorded under a participant's timeline (``[grupo] …``) are skipped. When
    ``covered`` is given, the jids that have entries in the period are added to it.
    """
    import os
    import re
    from datetime import datetime, timedelta, timezone

    from services.contact_filesystem import is_direct_jid, list_contact_dirs
    from services.contact_identity import canonical_jid
    from services.evolution_discovery import _registry_map, resolve_chat_label

    days = max(1, min(int(days), 30))
    limit = max(1, min(int(limit), 100))
    per_chat = int(os.getenv("EVI_WHATSAPP_RECENT_MSG_PER_CHAT", "15"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    registry = None
    rows: list[dict] = []
    for d in list_contact_dirs():
        jid = d.name
        path = d / "timeline.jsonl"
        if not path.is_file() or not is_direct_jid(jid) or canonical_jid(jid) != jid:
            continue
        entries = _recent_entries(path, cutoff)
        # A commitment row duplicates the message that produced it (same source_id).
        msg_ids = {str(e.get("source_id")) for e in entries
                   if e.get("commitment_id") is None and e.get("source_id")}
        mine: list[dict] = []
        for e in entries:
            if e.get("commitment_id") is not None and str(e.get("source_id")) in msg_ids:
                continue
            preview = str(e.get("text_preview") or "").strip()
            if preview.startswith("[grupo]"):
                continue
            mine.append((e, preview))
        if not mine:
            continue
        if covered is not None:
            covered.add(jid)
        if registry is None:
            registry = _registry_map()
        mine.sort(key=lambda t: t[0]["_ts_dt"], reverse=True)
        raw_label = ""
        for _, preview in mine:
            m = re.match(r"^\[([^\]]*)\]\s*", preview)
            if m and not preview.startswith("[eu]"):
                raw_label = m.group(1)
                break
        chat_label, chat_phone = resolve_chat_label(jid, raw_label, registry)
        for e, preview in mine[:per_chat]:
            from_me = preview.startswith("[eu]")
            if from_me:
                text = preview[4:].strip()
            else:
                m = re.match(r"^\[([^\]]*)\]\s*", preview)
                text = preview[m.end():] if m else preview
            rows.append({
                "ts": e.get("ts"),
                "ts_dt": e["_ts_dt"],
                "chat_jid": jid,
                "chat_label": chat_label,
                "chat_phone": chat_phone,
                "participant": "",
                "sender_label": chat_label,
                "from_me": from_me,
                "text": text,
                "preview": preview,
                "message_id": str(e.get("source_id") or ""),
            })
    rows.sort(key=lambda r: r["ts_dt"], reverse=True)
    return rows[:limit]
