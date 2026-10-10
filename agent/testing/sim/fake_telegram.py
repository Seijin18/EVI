"""Fake Telegram Bot API for the EVI simulation harness.

Paths ``/bot<token>/<method>`` (GET or POST; params from query, JSON or form).
Only the token ``sim-token`` is accepted (401 otherwise, like Telegram).

* ``getMe`` / ``deleteWebhook``  canned ``{"ok": true, "result": ...}``;
* ``getUpdates``  queue fed by the runner (``enqueue``); honours ``offset``
                  (acks everything below it) and ``timeout`` (long poll: blocks
                  up to ``timeout`` s until an update is available);
* ``sendMessage`` captured in ``sent``; ``set_fault("sendMessage", "transient",
                  count=N)`` makes the next N calls answer 500 (or 429 for
                  ``"rate_limit"``) - what ``services.send_result.post_with_retry``
                  treats as transient (5xx / transport; a 4xx is NOT retried,
                  so 429 is only for exercising the no-retry path).
* ``getFile``     file_path for a file registered by the runner (``register_file``);
* ``GET /file/bot<token>/<path>`` serves the registered bytes (``file_bytes``);
* any other method -> 500 naming it (fail loudly).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

SIM_TOKEN = "sim-token"
BOT_ID = 8000000001
FAULTS = ("transient", "rate_limit")


def _ok(result: Any) -> dict:
    return {"ok": True, "result": result}


class FakeTelegram:
    def __init__(self, token: str = SIM_TOKEN, default_chat_id: str | int | None = None) -> None:
        self.token = token
        self._default_chat_id = default_chat_id
        # update ids stay monotonic across reset(): the agent's poller keeps its
        # getUpdates offset, so restarting at 1 would make it drop every new update
        self._update_seq = 0
        self.reset()

    @property
    def default_chat_id(self) -> int:
        raw = self._default_chat_id or os.environ.get("TELEGRAM_CHAT_ID") or 900000001
        return int(raw)

    # ------------------------------------------------------------- control
    def reset(self) -> None:
        self._updates: list[dict] = []
        self._message_seq = 0
        self.sent: list[dict] = []
        self._files: dict[str, dict] = {}  # file_id -> {"path", "data", "mime"}
        self._file_seq = 0
        self._faults: dict[str, dict] = {}

    def enqueue(self, text: str, chat_id: str | int | None = None, *, from_name: str = "Sim User") -> int:
        """Queue a private text message from the user; returns its update_id."""
        cid = int(chat_id if chat_id is not None else self.default_chat_id)
        self._update_seq += 1
        self._message_seq += 1
        self._updates.append(
            {
                "update_id": self._update_seq,
                "message": {
                    "message_id": self._message_seq,
                    "from": {
                        "id": cid,
                        "is_bot": False,
                        "first_name": from_name,
                        "language_code": "pt-br",
                    },
                    "chat": {"id": cid, "first_name": from_name, "type": "private"},
                    "date": int(time.time()),
                    "text": text,
                },
            }
        )
        return self._update_seq

    def register_file(self, data: bytes, mime: str = "audio/ogg") -> str:
        """Store bytes for getFile/download; returns the file_id."""
        self._file_seq += 1
        file_id = f"SIMFILE{self._file_seq}"
        ext = "oga" if "ogg" in mime else "bin"
        self._files[file_id] = {"path": f"voice/file_{self._file_seq}.{ext}", "data": bytes(data), "mime": mime}
        return file_id

    def enqueue_voice(
        self,
        data: bytes,
        chat_id: str | int | None = None,
        *,
        duration: int = 3,
        file_size: int | None = None,
        mime: str = "audio/ogg",
        from_name: str = "Sim User",
    ) -> int:
        """Register ``data`` and queue a private ``voice`` message from the user; returns its update_id."""
        file_id = self.register_file(data, mime)
        uid = self.enqueue("", chat_id, from_name=from_name)
        msg = self._updates[-1]["message"]
        del msg["text"]
        msg["voice"] = {
            "duration": int(duration),
            "mime_type": mime,
            "file_id": file_id,
            "file_unique_id": f"U{file_id}",
            "file_size": int(file_size if file_size is not None else len(data)),
        }
        return uid

    def file_bytes(self, file_path: str) -> tuple[bytes, str] | None:
        for f in self._files.values():
            if f["path"] == file_path.lstrip("/"):
                return f["data"], f["mime"]
        return None

    def set_fault(self, method: str, kind: str = "transient", count: int = 1) -> None:
        if kind not in FAULTS:
            raise ValueError(f"unknown telegram fault {kind!r}; expected one of {FAULTS}")
        if method != "sendMessage":
            raise ValueError("only sendMessage faults are supported")
        self._faults[method] = {"kind": kind, "count": int(count)}

    def state(self) -> dict:
        return {
            "pending_updates": list(self._updates),
            "sent": list(self.sent),
            "files": sorted(self._files),
            "faults": dict(self._faults),
        }

    # ------------------------------------------------------------- API
    def _take_fault(self, method: str) -> str | None:
        f = self._faults.get(method)
        if not f or f["count"] <= 0:
            return None
        f["count"] -= 1
        return f["kind"]

    def check_token(self, token: str) -> bool:
        return token == self.token

    def get_updates(self, offset: int | None) -> list[dict]:
        if offset is not None and offset > 0:
            self._updates = [u for u in self._updates if u["update_id"] >= offset]
        return list(self._updates)

    async def call(self, method: str, params: dict) -> tuple[int, dict]:
        if method == "getMe":
            return 200, _ok(
                {"id": BOT_ID, "is_bot": True, "first_name": "EVI Sim", "username": "evi_sim_bot"}
            )
        if method == "deleteWebhook":
            return 200, _ok(True)
        if method == "getUpdates":
            return 200, _ok(await self._long_poll(params))
        if method == "sendMessage":
            return self._send_message(params)
        if method == "getFile":
            return self._get_file(params)
        return 500, {
            "ok": False,
            "error_code": 500,
            "description": f"fake telegram: unsupported method {method}",
        }

    async def _long_poll(self, params: dict) -> list[dict]:
        try:
            offset = int(params["offset"]) if params.get("offset") not in (None, "") else None
        except (TypeError, ValueError):
            offset = None
        try:
            wait = float(params.get("timeout") or 0)
        except (TypeError, ValueError):
            wait = 0.0
        deadline = time.monotonic() + max(0.0, wait)
        while True:
            out = self.get_updates(offset)
            if out or time.monotonic() >= deadline:
                return out
            await asyncio.sleep(0.05)

    def _get_file(self, params: dict) -> tuple[int, dict]:
        f = self._files.get(str(params.get("file_id") or ""))
        if f is None:
            return 400, {"ok": False, "error_code": 400, "description": "Bad Request: wrong file_id or the file is temporarily unavailable"}
        return 200, _ok(
            {
                "file_id": params["file_id"],
                "file_unique_id": f"U{params['file_id']}",
                "file_size": len(f["data"]),
                "file_path": f["path"],
            }
        )

    def _send_message(self, params: dict) -> tuple[int, dict]:
        fault = self._take_fault("sendMessage")
        if fault == "transient":
            return 500, {"ok": False, "error_code": 500, "description": "Internal Server Error (sim fault)"}
        if fault == "rate_limit":
            return 429, {
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests: retry after 1",
                "parameters": {"retry_after": 1},
            }
        chat_id = params.get("chat_id")
        text = params.get("text")
        if chat_id in (None, ""):
            return 400, {"ok": False, "error_code": 400, "description": "Bad Request: chat_id is empty"}
        if not text:
            return 400, {"ok": False, "error_code": 400, "description": "Bad Request: message text is empty"}
        self._message_seq += 1
        try:
            cid: Any = int(chat_id)
        except (TypeError, ValueError):
            cid = chat_id
        msg = {
            "message_id": self._message_seq,
            "from": {"id": BOT_ID, "is_bot": True, "first_name": "EVI Sim", "username": "evi_sim_bot"},
            "chat": {"id": cid, "type": "private"},
            "date": int(time.time()),
            "text": text,
        }
        self.sent.append({**msg, "chat_id": cid, "params": dict(params)})
        return 200, _ok(msg)
