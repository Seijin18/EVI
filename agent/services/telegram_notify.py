"""Send Telegram notifications via Bot API."""

from __future__ import annotations

import json
import os
import urllib.request

from services.send_result import (
    EMPTY_TEXT,
    NOT_CONFIGURED,
    SendResult,
    post_with_retry,
)


def send_telegram_message(text: str, chat_id: str | int | None = None) -> SendResult:
    """Deliver a Telegram reply. Truthy on success; never raises.

    Returns a SendResult rather than a bare bool so a dropped reply carries a
    reason. `__bool__` keeps every existing `if send_telegram_message(...)` and
    `telegram_sent=` call site behaving exactly as before.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    target = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not target:
        missing = "TELEGRAM_BOT_TOKEN" if not token else "chat_id/TELEGRAM_CHAT_ID"
        return SendResult.fail(NOT_CONFIGURED, detail=f"missing {missing}")
    if not (text or "").strip():
        return SendResult.fail(EMPTY_TEXT)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps(
        {"chat_id": str(target), "text": text[:4000], "disable_web_page_preview": True}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return post_with_retry(req, timeout=15, context="telegram_notify.send_telegram_message")



from services.commitment_review.digest import format_pending_digest  # noqa: E402,F401
