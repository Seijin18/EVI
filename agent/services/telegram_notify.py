"""Send Telegram notifications via Bot API."""

from __future__ import annotations

import html
import json
import logging
import os
import re
import urllib.request

from services.send_result import (
    EMPTY_TEXT,
    HTTP_4XX,
    NOT_CONFIGURED,
    SendResult,
    post_with_retry,
)
from services.untrusted import has_marker, strip_markers

_log = logging.getLogger("evi.telegram_notify")
_TAG_RE = re.compile(r"</?(?:b|i|u|s|code|pre|a)(?:\s[^>]*)?>")
MAX_LEN = 4000


def telegram_api_base() -> str:
    """Bot API origin; read at call time. Override only for simulation."""
    return (os.getenv("TELEGRAM_API_BASE", "").strip() or "https://api.telegram.org").rstrip("/")


def html_to_plain(text: str) -> str:
    """Plain-text twin of a Telegram-HTML message (tags dropped, entities decoded)."""
    return html.unescape(_TAG_RE.sub("", text))


def _clip(text: str, html_mode: bool) -> str:
    if len(text) <= MAX_LEN:
        return text
    cut = text[:MAX_LEN]
    if html_mode and "\n" in cut:  # never cut inside a tag
        cut = cut[: cut.rfind("\n")]
    return cut


def _post(
    token: str,
    target: str | int,
    text: str,
    parse_mode: str | None,
    reply_markup: dict | None = None,
) -> SendResult:
    payload: dict = {"chat_id": str(target), "text": _clip(text, bool(parse_mode)),
                     "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    req = urllib.request.Request(
        f"{telegram_api_base()}/bot{token}/sendMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return post_with_retry(
        req,
        timeout=15,
        context="telegram_notify.send_telegram_message",
        body_hint=bool(parse_mode or reply_markup),
        capture_message_id=True,
    )


def _call(method: str, payload: dict) -> bool:
    """POST a Bot API method that only answers ok/not ok. Never raises."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return False
    req = urllib.request.Request(
        f"{telegram_api_base()}/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return bool(post_with_retry(req, timeout=15, context=f"telegram_notify.{method}"))


def answer_callback(callback_query_id: str, text: str = "") -> bool:
    """Answer a button tap (stops the client spinner; ``text`` shows as a toast)."""
    if not callback_query_id:
        return False
    payload: dict = {"callback_query_id": str(callback_query_id)}
    if text:
        payload["text"] = text[:200]
    return _call("answerCallbackQuery", payload)


def edit_reply_markup(chat_id: str | int, message_id: int, reply_markup: dict | None) -> bool:
    """Replace a message's inline keyboard; ``None`` removes it."""
    return _call(
        "editMessageReplyMarkup",
        {
            "chat_id": str(chat_id),
            "message_id": int(message_id),
            "reply_markup": reply_markup or {"inline_keyboard": []},
        },
    )


def send_telegram_message(
    text: str,
    chat_id: str | int | None = None,
    *,
    parse_mode: str | None = None,
    reply_markup: dict | None = None,
) -> SendResult:
    """Deliver a Telegram reply. Truthy on success; never raises.

    Returns a SendResult rather than a bare bool so a dropped reply carries a
    reason. `__bool__` keeps every existing `if send_telegram_message(...)` and
    `telegram_sent=` call site behaving exactly as before.

    Whatever the caller, a surviving ``«externo:…»`` marker (meant for the LLM) is
    stripped before sending and logged without its content. With
    ``parse_mode="HTML"`` a formatting rejection (HTTP 400 "can't parse entities")
    is retried once as plain text. ``reply_markup`` (inline keyboard) is sent with the
    text; if Telegram rejects the markup (HTTP 400 mentioning it) the text is resent
    without it. A successful result carries the sent ``message_id`` when known.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    target = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not target:
        missing = "TELEGRAM_BOT_TOKEN" if not token else "chat_id/TELEGRAM_CHAT_ID"
        return SendResult.fail(NOT_CONFIGURED, detail=f"missing {missing}")
    if has_marker(text):
        from services.soft_fail import soft_fail

        soft_fail("telegram_notify.marker_leak", RuntimeError("model marker in outgoing text"))
        text = strip_markers(text)
    if not (text or "").strip():
        return SendResult.fail(EMPTY_TEXT)

    result = _post(token, target, text, parse_mode, reply_markup)
    if not result and reply_markup and result.reason == HTTP_4XX and _markup_rejected(result):
        _log.warning("telegram rejected the inline keyboard; resending without it")
        reply_markup = None
        result = _post(token, target, text, parse_mode, None)
    if (
        not result
        and parse_mode
        and result.reason == HTTP_4XX
        and "parse entities" in result.detail.lower()
    ):
        _log.warning("telegram rejected %s formatting; resending as plain text", parse_mode)
        return _post(
            token, target, html_to_plain(text) if parse_mode == "HTML" else text, None, reply_markup
        )
    return result


def _markup_rejected(result: SendResult) -> bool:
    d = result.detail.lower()
    return "parse entities" not in d and ("reply markup" in d or "keyboard" in d or "button" in d or "reply_markup" in d)


from services.commitment_review.digest import format_pending_digest  # noqa: E402,F401
