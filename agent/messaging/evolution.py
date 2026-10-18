"""Evolution API messaging backend."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from services.send_result import (
    EMPTY_TEXT,
    NOT_CONFIGURED,
    SendResult,
    post_with_retry,
)

MEDIA_MAX_BYTES = 20 * 1024 * 1024


class MediaTooBig(Exception):
    """Downloaded media exceeds MEDIA_MAX_BYTES."""


_EVI_PREFIX = re.compile(r"^\[EVI\]\s*", re.I)


def reply_prefix() -> str:
    raw = os.getenv("EVI_WHATSAPP_REPLY_PREFIX", "[EVI]").strip() or "[EVI]"
    if not raw.endswith(" "):
        raw = f"{raw} "
    return raw


class EvolutionClient:
    """Sends and formats WhatsApp messages via Evolution API."""

    def _config(self) -> tuple[str, str, str]:
        base = os.getenv("EVOLUTION_SERVER_URL", "http://evolution-api:8080").rstrip("/")
        instance = os.getenv("EVOLUTION_INSTANCE_NAME", "evi").strip()
        api_key = os.getenv("EVOLUTION_API_KEY", "").strip()
        return base, instance, api_key

    def _post_json(self, path: str, payload: dict, *, timeout: int = 30) -> Any:
        base, _, api_key = self._config()
        if not base:
            return None
        url = f"{base}{path}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["apikey"] = api_key
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                if not body.strip():
                    return {}
                return json.loads(body)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
            return None

    def connection_state(self, *, timeout: int = 5) -> str | None:
        """Instance connection state ('open', 'close', 'connecting'…), lower-case.

        None on any failure (Evolution down, timeout, bad payload). Never raises.
        """
        base, instance, api_key = self._config()
        if not base or not instance:
            return None
        req = urllib.request.Request(
            f"{base}/instance/connectionState/{instance}",
            headers={"apikey": api_key} if api_key else {},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError):  # URLError/HTTPError/timeout are OSError
            return None
        inst = body.get("instance") if isinstance(body, dict) else None
        state = inst.get("state") if isinstance(inst, dict) else None
        return state.strip().lower() if isinstance(state, str) and state.strip() else None

    def find_messages(self, jid: str, *, limit: int | None = None) -> Any:
        """Fetch cached chat messages from Evolution DB (findMessages)."""
        _, instance, _ = self._config()
        if not instance or not jid:
            return None
        max_msgs = limit or int(os.getenv("EVI_BACKFILL_MAX_MESSAGES", "200"))
        payload = {
            "where": {"key": {"remoteJid": jid}},
            "page": 1,
            "offset": max_msgs,
        }
        return self._post_json(f"/chat/findMessages/{instance}", payload)

    def get_media_base64(self, message_key: dict) -> tuple[bytes, str] | None:
        """Download a message's media (Evolution getBase64FromMediaMessage).

        Returns (bytes, mimetype), or None on any failure. Raises MediaTooBig
        when the payload is over 20 MB.
        """
        import base64

        _, instance, _ = self._config()
        if not instance or not message_key:
            return None
        resp = self._post_json(
            f"/chat/getBase64FromMediaMessage/{instance}",
            {"message": {"key": message_key}, "convertToMp4": False},
            timeout=30,
        )
        if not isinstance(resp, dict):
            return None
        b64 = resp.get("base64")
        if not isinstance(b64, str) or not b64:
            return None
        if len(b64) > MEDIA_MAX_BYTES * 4 // 3 + 8:
            raise MediaTooBig()
        if b64.startswith("data:") and "," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            data = base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            return None
        if len(data) > MEDIA_MAX_BYTES:
            raise MediaTooBig()
        mime = str(resp.get("mimetype") or "audio/ogg").split(";")[0].strip() or "audio/ogg"
        return data, mime

    def find_contacts(self, *, limit: int | None = None) -> Any:
        _, instance, _ = self._config()
        if not instance:
            return None
        max_n = limit or int(os.getenv("EVI_EVOLUTION_CONTACTS_LIMIT", "3000"))
        return self._post_json(
            f"/chat/findContacts/{instance}",
            {"page": 1, "offset": max_n},
        )

    def find_chats(self, *, limit: int | None = None) -> Any:
        _, instance, _ = self._config()
        if not instance:
            return None
        max_n = limit or int(os.getenv("EVI_WHATSAPP_RECENT_MAX_CHATS", "30"))
        return self._post_json(
            f"/chat/findChats/{instance}",
            {"page": 1, "offset": max_n},
        )

    def send_text(self, jid: str, text: str, *, add_prefix: bool = True) -> SendResult:
        """Deliver a WhatsApp reply. Truthy on success; never raises.

        Same contract as the Telegram sender — see services/send_result.py.
        """
        base, instance, api_key = self._config()
        if not base or not instance or not jid:
            missing = "EVOLUTION_SERVER_URL" if not base else (
                "EVOLUTION_INSTANCE_NAME" if not instance else "jid"
            )
            return SendResult.fail(NOT_CONFIGURED, detail=f"missing {missing}")
        if not (text or "").strip():
            return SendResult.fail(EMPTY_TEXT)

        number = jid.split("@")[0]
        payload = {
            "number": number,
            "text": self.format_reply(text) if add_prefix else text[:4000],
        }
        url = f"{base}/message/sendText/{instance}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["apikey"] = api_key
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        return post_with_retry(req, timeout=20, context="evolution.send_text")

    def is_bot_message(self, text: str) -> bool:
        body = text.strip()
        prefix = reply_prefix()
        if body.startswith(prefix):
            return True
        return bool(_EVI_PREFIX.match(body))

    def format_reply(self, text: str) -> str:
        prefix = reply_prefix()
        body = text.strip()
        if body.startswith(prefix) or body.startswith(prefix.strip()):
            if body.startswith(prefix.strip()) and not body.startswith(prefix):
                body = prefix + body[len(prefix.strip()):].lstrip()
            return body[:4000]
        return f"{prefix}{body}"[:4000]
