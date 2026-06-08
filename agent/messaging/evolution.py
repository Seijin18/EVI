"""Evolution API messaging backend."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

_EVI_PREFIX = re.compile(r"^\[EVI\]\s*", re.I)


def reply_prefix() -> str:
    raw = os.getenv("EVI_WHATSAPP_REPLY_PREFIX", "[EVI]").strip() or "[EVI]"
    if not raw.endswith(" "):
        raw = f"{raw} "
    return raw


class EvolutionClient:
    """Sends and formats WhatsApp messages via Evolution API."""

    def send_text(self, jid: str, text: str, *, add_prefix: bool = True) -> bool:
        base = os.getenv("EVOLUTION_SERVER_URL", "http://evolution-api:8080").rstrip("/")
        instance = os.getenv("EVOLUTION_INSTANCE_NAME", "evi").strip()
        api_key = os.getenv("EVOLUTION_API_KEY", "").strip()
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
