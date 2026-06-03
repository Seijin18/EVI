"""Map Evolution API webhook payloads to IncomingMessage."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.message_sources import IncomingMessage


def _text_from_message(data: Dict[str, Any]) -> str:
    msg = data.get("message") or data
    if isinstance(msg.get("conversation"), str):
        return msg["conversation"]
    if msg.get("extendedTextMessage"):
        return msg["extendedTextMessage"].get("text", "")
    if msg.get("imageMessage") and msg["imageMessage"].get("caption"):
        return msg["imageMessage"]["caption"]
    return str(msg.get("text") or "")


def parse_evolution_webhook(body: Dict[str, Any]) -> List[IncomingMessage]:
    """Handle MESSAGES_UPSERT style payloads (v2 flexible)."""
    results: List[IncomingMessage] = []

    event = body.get("event") or body.get("type") or ""
    if event and "message" not in event.lower() and "upsert" not in event.lower():
        if body.get("data") is None and not body.get("messages"):
            return results

    data = body.get("data") or body
    messages = data.get("messages") or data.get("message")
    if messages is None:
        messages = [data] if data.get("key") or data.get("message") else []
    if isinstance(messages, dict):
        messages = [messages]

    for idx, item in enumerate(messages):
        if not isinstance(item, dict):
            continue
        key = item.get("key") or {}
        msg_id = key.get("id") or item.get("id") or f"evo_{idx}"
        sender = (
            key.get("remoteJid")
            or item.get("from")
            or item.get("pushName")
            or "unknown"
        )
        text = _text_from_message(item)
        if not text.strip():
            continue
        ts = str(
            item.get("messageTimestamp")
            or item.get("timestamp")
            or body.get("date_time")
            or ""
        )
        if ts.isdigit():
            from datetime import datetime

            ts = datetime.utcfromtimestamp(int(ts)).isoformat()
        results.append(
            IncomingMessage(id=str(msg_id), sender=str(sender), text=text, ts=ts or "")
        )
    return results
