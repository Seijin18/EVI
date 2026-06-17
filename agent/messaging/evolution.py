"""Evolution API messaging backend."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

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

    def find_contacts(self, *, limit: int | None = None) -> Any:
        _, instance, _ = self._config()
        if not instance:
            return None
        max_n = limit or int(os.getenv("EVI_EVOLUTION_CONTACTS_LIMIT", "300"))
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

    def send_text(self, jid: str, text: str, *, add_prefix: bool = True) -> bool:
        base, instance, api_key = self._config()
        if not base or not instance or not jid:
            return False
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
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            return False

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
