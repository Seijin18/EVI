"""Fake Evolution API (WhatsApp) for the EVI simulation harness.

Serves exactly what ``messaging.evolution.EvolutionClient`` calls:

* ``POST /message/sendText/<instance>``   captured WITH the recipient
  (``number``) so scenarios can assert that nothing reaches a third party;
* ``GET  /instance/connectionState/<instance>``  ``{"instance": {"instanceName", "state"}}``;
  the state is seed ``state`` (default ``open``; e.g. ``close``) or ``set_state``;
* ``POST /chat/findContacts/<instance>``  from seed ``contacts``;
* ``POST /chat/findChats/<instance>``     from seed ``chats``;
* ``POST /chat/findMessages/<instance>``  from seed ``messages`` (``{jid: [..]}``),
  filtered by ``where.key.remoteJid``;
* ``POST /chat/fetchProfile/<instance>``  from seed ``profiles`` (``{number: {..}}``);
* ``POST /chat/getBase64FromMediaMessage/<instance>``  media registered by the runner
  (``register_media``) and served by ``message.key.id``; every request is logged in
  ``media_requests`` (so a scenario can prove nothing was fetched).

When ``apikey`` is set (``EVOLUTION_API_KEY``) a request carrying a different
``apikey`` header gets 401. Anything else -> 500 naming the URL.
"""

from __future__ import annotations

import copy
import os
import time
from typing import Any

ENDPOINTS = {
    "message/sendText",
    "chat/findContacts",
    "chat/findChats",
    "chat/findMessages",
    "chat/fetchProfile",
    "chat/getBase64FromMediaMessage",
}


class FakeEvolution:
    def __init__(self, apikey: str | None = None, instance: str | None = None) -> None:
        self._apikey = apikey
        self._instance = instance
        self.reset()

    @property
    def apikey(self) -> str:
        return (self._apikey if self._apikey is not None else os.environ.get("EVOLUTION_API_KEY", "")).strip()

    def reset(self) -> None:
        self.sent: list[dict] = []
        self._contacts: list[dict] = []
        self._chats: list[dict] = []
        self._messages: dict[str, list[dict]] = {}
        self._profiles: dict[str, dict] = {}
        self._seq = 0
        self.connection_state = "open"
        self._media: dict[str, dict] = {}  # message id -> {"data": bytes, "mimetype": str}
        self.media_requests: list[dict] = []

    def register_media(self, message_id: str, data: bytes, mimetype: str = "audio/ogg; codecs=opus") -> None:
        self._media[str(message_id)] = {"data": bytes(data), "mimetype": mimetype}

    def seed(self, data: dict) -> None:
        """Replace contacts/chats/messages/profiles (captures are kept)."""
        self._contacts = [dict(c) for c in data.get("contacts") or []]
        self._chats = [dict(c) for c in data.get("chats") or []]
        self._messages = {k: [dict(m) for m in v] for k, v in (data.get("messages") or {}).items()}
        self._profiles = {str(k): dict(v) for k, v in (data.get("profiles") or {}).items()}
        self.connection_state = str(data.get("state") or "open")

    def set_state(self, state: str) -> None:
        """Change the WhatsApp session state mid-scenario (``open`` / ``close`` / ``connecting``)."""
        self.connection_state = str(state or "open")

    def record_message(self, record: dict) -> None:
        """Append a message the runner just delivered by webhook, so findMessages serves it
        back (same record shape as the webhook: key / messageTimestamp / message / pushName)."""
        jid = str((record.get("key") or {}).get("remoteJid") or "")
        if jid:
            self._messages.setdefault(jid, []).append(copy.deepcopy(record))

    def state(self) -> dict:
        return copy.deepcopy(
            {
                "sent": self.sent,
                "media_requests": self.media_requests,
                "contacts": self._contacts,
                "chats": self._chats,
                "messages": self._messages,
                "profiles": self._profiles,
                "connection_state": self.connection_state,
            }
        )

    # ------------------------------------------------------------- API
    def handle(self, method: str, path: str, headers: dict[str, str], body: Any) -> tuple[int, Any]:
        key = self.apikey
        if key and {k.lower(): v for k, v in headers.items()}.get("apikey") != key:
            return 401, {"status": 401, "error": "Unauthorized", "response": {"message": "Invalid apikey"}}
        parts = path.strip("/").split("/")
        if method == "GET" and len(parts) == 3 and parts[:2] == ["instance", "connectionState"]:
            return 200, {"instance": {"instanceName": parts[2], "state": self.connection_state}}
        if method != "POST" or len(parts) != 3 or "/".join(parts[:2]) not in ENDPOINTS:
            return self._unknown(method, path)
        endpoint = "/".join(parts[:2])
        payload = body if isinstance(body, dict) else {}
        if endpoint == "message/sendText":
            return self._send_text(payload)
        if endpoint == "chat/findContacts":
            return 200, copy.deepcopy(self._contacts)
        if endpoint == "chat/findChats":
            return 200, copy.deepcopy(self._chats)
        if endpoint == "chat/findMessages":
            jid = ((payload.get("where") or {}).get("key") or {}).get("remoteJid")
            rows = self._messages.get(jid, []) if jid else [m for v in self._messages.values() for m in v]
            return 200, {"messages": {"total": len(rows), "pages": 1, "currentPage": 1, "records": copy.deepcopy(rows)}}
        if endpoint == "chat/getBase64FromMediaMessage":
            return self._get_media(payload)
        number = str(payload.get("number") or "").split("@")[0]
        return 200, copy.deepcopy(self._profiles.get(number, {"wuid": f"{number}@s.whatsapp.net"}))

    @staticmethod
    def _unknown(method: str, path: str) -> tuple[int, Any]:
        return 500, {"error": f"fake evolution: unsupported endpoint {method} {path}"}

    def _get_media(self, payload: dict) -> tuple[int, Any]:
        import base64

        key = (payload.get("message") or {}).get("key") or {}
        mid = str(key.get("id") or "")
        self.media_requests.append({"id": mid, "remoteJid": key.get("remoteJid"), "ts": int(time.time())})
        media = self._media.get(mid)
        if media is None:
            return 404, {"status": 404, "error": "Not Found", "response": {"message": [f"Message not found: {mid}"]}}
        return 201, {
            "mediaType": "audioMessage",
            "mimetype": media["mimetype"],
            "base64": base64.b64encode(media["data"]).decode("ascii"),
        }

    def _send_text(self, payload: dict) -> tuple[int, Any]:
        number = payload.get("number")
        text = payload.get("text")
        if not number or not text:
            return 400, {"status": 400, "error": "Bad Request", "response": {"message": ["number and text required"]}}
        self._seq += 1
        jid = number if "@" in str(number) else f"{number}@s.whatsapp.net"
        rec = {"number": str(number), "jid": jid, "text": text, "ts": int(time.time()), "id": f"SIMMSG{self._seq}"}
        self.sent.append(rec)
        return 201, {
            "key": {"remoteJid": jid, "fromMe": True, "id": rec["id"]},
            "message": {"conversation": text},
            "messageTimestamp": rec["ts"],
            "status": "PENDING",
        }
