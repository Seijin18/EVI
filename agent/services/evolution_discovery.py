"""Discover WhatsApp contacts and recent messages via Evolution API."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from messaging.evolution import EvolutionClient
from services.evolution_parser import parse_evolution_message_list


def _as_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("contacts", "chats", "data", "records"):
            inner = raw.get(key)
            if isinstance(inner, list):
                return inner
            if isinstance(inner, dict):
                for sub in ("records", "contacts", "chats"):
                    rows = inner.get(sub)
                    if isinstance(rows, list):
                        return rows
        if raw.get("id") or raw.get("remoteJid") or raw.get("key"):
            return [raw]
    return []


def _contact_jid(row: dict[str, Any]) -> str:
    for key in ("remoteJid", "id", "jid"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    key_obj = row.get("key")
    if isinstance(key_obj, dict):
        rj = key_obj.get("remoteJid") or key_obj.get("id")
        if isinstance(rj, str):
            return rj.strip()
    return ""


def _contact_label(row: dict[str, Any]) -> str:
    for key in ("pushName", "name", "verifiedName", "notify"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _chat_jid(row: dict[str, Any]) -> str:
    for key in ("remoteJid", "id", "jid"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return _contact_jid(row)


def _chat_label(row: dict[str, Any]) -> str:
    for key in ("name", "pushName", "chatName"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return _contact_label(row)


def _query_tokens(query: str) -> list[str]:
    return [t for t in re.split(r"\s+", (query or "").casefold().strip()) if len(t) >= 2]


def name_query_matches(label: str, query: str) -> bool:
    if not label or not query:
        return False
    label_cf = label.casefold().strip()
    q_cf = query.casefold().strip()
    if label_cf == q_cf:
        return True
    if len(label_cf) >= 3 and label_cf in q_cf:
        return True
    if len(q_cf) >= 3 and q_cf in label_cf:
        return True
    tokens = _query_tokens(query)
    if len(tokens) >= 2:
        return all(token in label_cf for token in tokens)
    if len(tokens) == 1 and len(tokens[0]) >= 3:
        return tokens[0] in label_cf
    return False


def fetch_evolution_contacts(*, limit: int | None = None) -> list[dict[str, Any]]:
    if os.getenv("EVI_EVOLUTION_DISCOVER_CONTACTS", "true").lower() not in (
        "1",
        "true",
        "yes",
    ):
        return []
    raw = EvolutionClient().find_contacts(limit=limit)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _as_list(raw):
        if not isinstance(row, dict):
            continue
        jid = _contact_jid(row)
        if not jid or jid in seen or jid.endswith("@lid"):
            continue
        seen.add(jid)
        label = _contact_label(row) or jid.split("@", 1)[0]
        out.append(
            {
                "jid": jid,
                "label": label,
                "source": "evolution",
            }
        )
    return out


def search_evolution_contacts(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for c in fetch_evolution_contacts():
        label = c.get("label") or ""
        if label.casefold() == q.casefold():
            scored.append((100, c))
        elif name_query_matches(label, q):
            scored.append((80, c))
    scored.sort(key=lambda x: (-x[0], (x[1].get("label") or "").casefold()))
    return [c for _, c in scored[:limit]]


def fetch_evolution_chats(*, limit: int | None = None) -> list[dict[str, Any]]:
    raw = EvolutionClient().find_chats(limit=limit)
    out: list[dict[str, Any]] = []
    for row in _as_list(raw):
        if not isinstance(row, dict):
            continue
        jid = _chat_jid(row)
        if not jid:
            continue
        out.append({"jid": jid, "label": _chat_label(row) or jid})
    return out


def _parse_msg_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.isdigit():
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OSError):
        return None


def _group_whitelist() -> set[str]:
    raw = os.getenv("EVI_WHATSAPP_GROUP_WHITELIST", "").strip()
    return {p.strip() for p in raw.split(",") if p.strip()}


def fetch_recent_whatsapp_messages(
    *,
    days: int = 1,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Recent messages across direct chats (+ whitelisted groups) from Evolution cache."""
    days = max(1, min(int(days), 30))
    limit = max(1, min(int(limit), 100))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    client = EvolutionClient()
    per_chat = int(os.getenv("EVI_WHATSAPP_RECENT_MSG_PER_CHAT", "15"))
    whitelist = _group_whitelist()
    skip_groups = os.getenv("EVI_WHATSAPP_SKIP_GROUPS", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    rows: list[dict[str, Any]] = []
    for chat in fetch_evolution_chats():
        jid = chat["jid"]
        is_group = "@g.us" in jid
        if is_group and skip_groups and jid not in whitelist:
            continue
        raw = client.find_messages(jid, limit=per_chat)
        if raw is None:
            continue
        chat_label = chat.get("label") or jid
        for msg in parse_evolution_message_list(raw, remote_jid=jid):
            ts_dt = _parse_msg_ts(msg.ts)
            if ts_dt and ts_dt < cutoff:
                continue
            who = msg.label or chat_label
            if msg.from_me:
                preview = f"[eu] {msg.text[:300]}"
            elif msg.is_group and who:
                preview = f"[{who}] {msg.text[:300]}"
            else:
                preview = msg.text[:300]
            rows.append(
                {
                    "ts": msg.ts,
                    "ts_dt": ts_dt,
                    "chat_jid": jid,
                    "chat_label": chat_label,
                    "participant": msg.participant,
                    "sender_label": who,
                    "from_me": msg.from_me,
                    "text": msg.text,
                    "preview": preview,
                    "message_id": msg.id,
                }
            )

    rows.sort(
        key=lambda r: r.get("ts_dt") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return rows[:limit]
