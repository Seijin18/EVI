"""Map Evolution API webhook payloads to IncomingMessage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from services.message_sources import IncomingMessage


def _text_from_message(data: Dict[str, Any]) -> str:
    msg = data.get("message") or data
    if isinstance(msg.get("conversation"), str):
        return msg["conversation"]
    if msg.get("extendedTextMessage"):
        ext = msg["extendedTextMessage"]
        return ext.get("text") or ext.get("matchedText") or ""
    if msg.get("imageMessage") and msg["imageMessage"].get("caption"):
        return msg["imageMessage"]["caption"]
    if msg.get("buttonsResponseMessage"):
        return msg["buttonsResponseMessage"].get("selectedDisplayText", "")
    if msg.get("listResponseMessage"):
        selected = msg["listResponseMessage"].get("singleSelectReply") or {}
        return selected.get("title", "")
    return str(msg.get("text") or "")


def _normalize_messages(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    if data.get("messages") is not None:
        raw = data["messages"]
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            return [raw]

    # Single message envelope: {key, message, messageTimestamp, ...}
    if data.get("key") or data.get("messageTimestamp"):
        return [data]

    # Legacy fallback: bare inner message dict only
    if data.get("message") and isinstance(data["message"], dict):
        return [data]

    return []


def _records_to_messages(
    messages: List[Dict[str, Any]],
    *,
    default_remote: str = "",
) -> List[IncomingMessage]:
    results: List[IncomingMessage] = []
    for idx, item in enumerate(messages):
        key = item.get("key") or {}
        msg_id = key.get("id") or item.get("id") or f"evo_{idx}"
        remote = str(
            key.get("remoteJid")
            or item.get("remoteJid")
            or item.get("from")
            or default_remote
            or "unknown"
        )
        sender = remote
        from_me = bool(key.get("fromMe") or item.get("fromMe"))
        is_group = "@g.us" in remote
        text = _text_from_message(item)
        if not text.strip():
            continue
        label = str(item.get("pushName") or key.get("pushName") or "")
        participant = str(key.get("participant") or item.get("participant") or "")
        ts = str(
            item.get("messageTimestamp")
            or item.get("timestamp")
            or item.get("createdAt")
            or ""
        )
        if ts.isdigit():
            ts = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        results.append(
            IncomingMessage(
                id=str(msg_id),
                sender=str(sender),
                text=text,
                ts=ts or "",
                from_me=from_me,
                is_group=is_group,
                label=label,
                participant=participant,
            )
        )
    return results


def _extract_message_records(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    for key in ("messages", "data"):
        inner = data.get(key)
        if isinstance(inner, list):
            return [item for item in inner if isinstance(item, dict)]
        if isinstance(inner, dict):
            for sub in ("records", "messages"):
                records = inner.get(sub)
                if isinstance(records, list):
                    return [item for item in records if isinstance(item, dict)]
            if inner.get("key") or inner.get("messageTimestamp"):
                return [inner]

    return _normalize_messages(data)


def parse_evolution_message_list(data: Any, *, remote_jid: str = "") -> List[IncomingMessage]:
    """Parse Evolution findMessages / DB payloads (no webhook event envelope)."""
    return _records_to_messages(
        _extract_message_records(data),
        default_remote=remote_jid,
    )


def parse_evolution_webhook(body: Dict[str, Any]) -> List[IncomingMessage]:
    """Handle MESSAGES_UPSERT style payloads (Evolution v2.1–v2.3)."""
    results: List[IncomingMessage] = []

    event = (body.get("event") or body.get("type") or "").lower()
    if event and "message" not in event and "upsert" not in event:
        return results

    data = body.get("data") or body
    messages = _normalize_messages(data)
    return _records_to_messages(messages)
