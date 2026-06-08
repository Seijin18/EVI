"""Send Telegram notifications via Bot API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def send_telegram_message(text: str, chat_id: str | int | None = None) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    target = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not target:
        return False
    chat_id = str(target)
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



from services.commitment_review.digest import format_pending_digest  # noqa: E402,F401
