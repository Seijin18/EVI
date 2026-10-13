"""Discover WhatsApp contacts and recent messages via Evolution API."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from messaging.evolution import EvolutionClient
from services.evolution_parser import _extract_message_records, parse_evolution_message_list


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


# --- Display names for chats -------------------------------------------------
# Evolution labels many chats with a bare number or JID ("5511…@s.whatsapp.net"),
# and 'LID' chats ("…@lid") hide the phone number. Resolve a readable name:
# address-book name (whatsapp_contacts.display_name) > WhatsApp profile name >
# formatted phone number. Never the raw JID.

_NOISE_JID_SUFFIXES = ("@newsletter", "status@broadcast")


def pretty_phone(jid_or_number: str) -> str:
    """'5511955550209@s.whatsapp.net' -> '+55 11 95555-0209' ('' if not a phone)."""
    digits = re.sub(r"\D", "", (jid_or_number or "").split("@", 1)[0])
    if len(digits) < 8:
        return ""
    if digits.startswith("55") and len(digits) in (12, 13):
        ddd, rest = digits[2:4], digits[4:]
        return f"+55 {ddd} {rest[:-4]}-{rest[-4:]}"
    return f"+{digits}"


def _looks_like_id(label: str) -> bool:
    base = (label or "").split("@", 1)[0]
    return not base.strip() or re.fullmatch(r"[\d\s+\-().]+", base.strip()) is not None


def _alt_phone_jid(records: list[Any], jid: str = "") -> str:
    """Phone JID of a LID chat, from key.remoteJidAlt of a message of that chat
    (when ``jid`` is given, the record's key.remoteJid must match it)."""
    for rec in records:
        key = rec.get("key") if isinstance(rec, dict) else None
        if jid and isinstance(key, dict) and key.get("remoteJid") not in (None, "", jid):
            continue
        alt = (key or {}).get("remoteJidAlt") if isinstance(key, dict) else ""
        if isinstance(alt, str) and alt.endswith("@s.whatsapp.net"):
            return alt
    return ""


def _registry_map() -> dict[str, dict[str, Any]]:
    try:
        from services.contact_registry import db_contacts_map

        return db_contacts_map()
    except Exception as exc:
        from services.soft_fail import soft_fail

        soft_fail("evolution_discovery.registry_map", exc)
        return {}


def resolve_chat_label(
    jid: str,
    raw_label: str,
    registry: dict[str, dict[str, Any]],
    alt_jid: str = "",
) -> tuple[str, str]:
    """(display label, formatted phone) for a chat; the label is never a raw JID."""
    from services.contact_registry import effective_label

    is_group = "@g.us" in jid
    phone_jid = "" if is_group else (jid if jid.endswith("@s.whatsapp.net") else alt_jid)
    if not phone_jid and jid.endswith("@lid"):
        from services.contact_identity import canonical_jid

        paired = canonical_jid(jid)
        phone_jid = paired if paired.endswith("@s.whatsapp.net") else ""
    row = registry.get(phone_jid) or registry.get(jid)
    name = effective_label(row, "")
    if _looks_like_id(name):
        name = ""
    if not name and not _looks_like_id(raw_label):
        name = raw_label.strip()
    phone = pretty_phone(phone_jid)
    if not name:
        name = phone or ("Grupo sem nome" if is_group else "Contato sem nome")
    return name, ("" if name == phone else phone)


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

    include_channels = os.getenv("EVI_WHATSAPP_INCLUDE_CHANNELS", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    registry = _registry_map()

    rows: list[dict[str, Any]] = []
    for chat in fetch_evolution_chats():
        jid = chat["jid"]
        is_group = "@g.us" in jid
        if is_group and skip_groups and jid not in whitelist:
            continue
        if not include_channels and jid.endswith(_NOISE_JID_SUFFIXES):
            continue  # news channels / status updates are not conversations
        raw = client.find_messages(jid, limit=per_chat)
        if raw is None:
            continue
        alt = _alt_phone_jid(_extract_message_records(raw), jid) if jid.endswith("@lid") else ""
        chat_label, chat_phone = resolve_chat_label(jid, chat.get("label") or "", registry, alt)
        for msg in parse_evolution_message_list(raw, remote_jid=jid):
            ts_dt = _parse_msg_ts(msg.ts)
            if ts_dt and ts_dt < cutoff:
                continue
            who = chat_label
            if is_group:
                part = (msg.participant or "").strip()
                prow = registry.get(part) if part.endswith("@s.whatsapp.net") else None
                who = (
                    (prow or {}).get("display_name")
                    or msg.label
                    or pretty_phone(part)
                    or "Alguém"
                )
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
                    "chat_phone": chat_phone,
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
