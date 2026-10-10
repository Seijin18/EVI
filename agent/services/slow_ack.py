"""Slow-tool ack (evi-perceived-reliability §3).

Armed by `TurnCollector.on_tool_start`: if a tool is still running after
`EVI_SLOW_ACK_SEC` seconds, one "⏳ fazendo… (<tool>)" message goes out through
the turn's own channel (Telegram chat or WhatsApp control JID, both encoded in
the session id). At most once per turn; cancelled when every running tool ends.
Off when the env is 0/unset; never for API or test turns. Soft-fails always.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from services.soft_fail import soft_fail

FRIENDLY_DEFAULT = "trabalhando nisso"
_FRIENDLY = {
    "summarize_inbox": "lendo seus e-mails",
    "schedule_event": "agendando",
    "list_calendar_events": "vendo sua agenda",
    "create_task": "criando a tarefa",
}


def slow_ack_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("EVI_SLOW_ACK_SEC", "0") or 0))
    except ValueError:
        return 0.0


def friendly_tool_name(tool: str) -> str:
    if tool in _FRIENDLY:
        return _FRIENDLY[tool]
    if tool.startswith("delete_emails"):
        return "apagando e-mails"
    return FRIENDLY_DEFAULT


def _send(channel: str | None, session_id: str | None, text: str) -> None:
    sid = session_id or ""
    if channel == "telegram" and sid.startswith("telegram-"):
        from services.telegram_notify import send_telegram_message

        send_telegram_message(text, chat_id=sid[len("telegram-"):])
    elif channel == "whatsapp_control" and sid.startswith("whatsapp-"):
        from services.evolution_client import send_whatsapp_text

        send_whatsapp_text(sid[len("whatsapp-"):], text, add_prefix=True)


class SlowAck:
    def __init__(self, collector: Any) -> None:
        self._collector = collector
        self._lock = threading.Lock()
        self._running: dict[Any, str] = {}
        self._timer: threading.Timer | None = None
        self._sent = False
        self._closed = False

    def _eligible(self) -> bool:
        c = self._collector
        return (
            getattr(c, "channel", None) in ("telegram", "whatsapp_control")
            and not getattr(c, "is_test", False)
        )

    def tool_started(self, key: Any, tool: str) -> None:
        try:
            delay = slow_ack_seconds()
            if delay <= 0 or not self._eligible():
                return
            with self._lock:
                if self._closed or self._sent:
                    return
                self._running[key] = tool
                if self._timer is None:
                    self._timer = threading.Timer(delay, self._fire)
                    self._timer.daemon = True
                    self._timer.start()
        except Exception as exc:
            soft_fail("slow_ack.tool_started", exc)

    def tool_ended(self, key: Any) -> None:
        try:
            with self._lock:
                self._running.pop(key, None)
                if not self._running:
                    self._cancel_locked()
        except Exception as exc:
            soft_fail("slow_ack.tool_ended", exc)

    def cancel(self) -> None:
        with self._lock:
            self._closed = True
            self._running.clear()
            self._cancel_locked()

    def _cancel_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fire(self) -> None:
        try:
            with self._lock:
                self._timer = None
                if self._closed or self._sent or not self._running:
                    return
                tool = next(iter(self._running.values()))
                self._sent = True
            c = self._collector
            _send(c.channel, c.session_id, f"⏳ fazendo… ({friendly_tool_name(tool)})")
        except Exception as exc:
            soft_fail("slow_ack.fire", exc)
