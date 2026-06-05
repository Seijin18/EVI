"""Send Telegram notifications via Bot API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List


def send_telegram_message(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps(
        {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def format_pending_digest(rows: List[dict]) -> str:
    lines = ["EVI: novos compromissos WhatsApp pendentes:"]
    for r in rows[:10]:
        pr = r.get("priority", "normal")
        lines.append(
            f"• [{r['id']}] ({pr}) {r['title']} — {r.get('event_date') or r.get('due_date') or 'sem data'}"
        )
    lines.append("No chat: peça para listar/confirmar compromissos pendentes.")
    return "\n".join(lines)
