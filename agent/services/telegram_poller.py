"""Telegram long polling (getUpdates) — no public URL or tunnel required."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from services.telegram_handler import ChatInvoke, process_telegram_update
from services.telegram_notify import telegram_api_base

logger = logging.getLogger("evi.telegram_poller")

ALLOWED_UPDATES = ["message", "callback_query", "message_reaction"]  # buttons; 👍/👎 reactions

_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def _api_get(token: str, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = f"{telegram_api_base()}/bot{token}/{method}"
    if qs:
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram API error"))
    return data


def _scrub(text: object, token: str) -> str:
    """Remove the bot token (present in every Bot API URL) from text meant for logs/replies."""
    out = str(text)
    return out.replace(token, "<token>") if token else out


def get_file_path(token: str, file_id: str) -> str:
    """Resolve a Telegram file_id to its download path via getFile. Errors never carry the token."""
    try:
        data = _api_get(token, "getFile", {"file_id": file_id})
    except Exception as exc:
        raise RuntimeError(f"getFile failed: {_scrub(exc, token)}") from None
    path = (data.get("result") or {}).get("file_path")
    if not path:
        raise RuntimeError("getFile returned no file_path")
    return str(path)


def download_file(token: str, file_path: str, max_bytes: int) -> bytes:
    """Download a file by path, aborting once it passes max_bytes. Errors never carry the token."""
    url = f"{telegram_api_base()}/file/bot{token}/{file_path.lstrip('/')}"
    try:
        req = urllib.request.Request(url, method="GET")
        buf = bytearray()
        with urllib.request.urlopen(req, timeout=30) as resp:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise ValueError(f"file exceeds {max_bytes} bytes")
    except Exception as exc:
        raise RuntimeError(f"download failed: {_scrub(exc, token)}") from None
    return bytes(buf)


def delete_webhook(token: str, drop_pending: bool = False) -> bool:
    try:
        _api_get(token, "deleteWebhook", {"drop_pending_updates": str(drop_pending).lower()})
        logger.info("Telegram webhook removed (polling mode)")
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError) as e:
        logger.warning("deleteWebhook failed: %s", e)
        return False


def fetch_updates(token: str, offset: int = 0, timeout: int = 30) -> List[Dict[str, Any]]:
    data = _api_get(
        token,
        "getUpdates",
        {"offset": offset, "timeout": timeout, "allowed_updates": json.dumps(ALLOWED_UPDATES)},
    )
    return data.get("result") or []


def _poll_loop(
    token: str,
    invoke_chat: ChatInvoke,
    reset_session: Callable[[str], None] | None = None,
    compact_session: Callable[[str], None] | None = None,
) -> None:
    offset = 0
    delete_webhook(token)
    print("EVI: Telegram poller started (long polling)", flush=True)
    logger.info("Telegram poller started (long polling)")
    while not _stop.is_set():
        try:
            updates = fetch_updates(token, offset=offset, timeout=30)
            for update in updates:
                uid = update.get("update_id")
                if uid is not None:
                    offset = int(uid) + 1
                try:
                    out = process_telegram_update(
                        update,
                        invoke_chat,
                        reset_session=reset_session,
                        compact_session=compact_session,
                    )
                    logger.info(
                        "update %s session=%s sent=%s",
                        uid,
                        out.get("session_id"),
                        out.get("telegram_sent"),
                    )
                except Exception:
                    logger.exception("failed to process update %s", uid)
        except Exception:
            logger.exception("getUpdates error; retry in 5s")
            time.sleep(5)


def start_poller(
    invoke_chat: ChatInvoke,
    token: Optional[str] = None,
    *,
    reset_session: Callable[[str], None] | None = None,
    compact_session: Callable[[str], None] | None = None,
) -> bool:
    """Start background long-polling thread. Idempotent."""
    global _thread
    tok = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    if not tok:
        logger.warning("TELEGRAM_BOT_TOKEN unset; poller not started")
        return False
    if _thread and _thread.is_alive():
        return True
    _stop.clear()
    _thread = threading.Thread(
        target=_poll_loop,
        args=(tok, invoke_chat, reset_session, compact_session),
        name="telegram-poller",
        daemon=True,
    )
    _thread.start()
    return True


def stop_poller() -> None:
    _stop.set()
