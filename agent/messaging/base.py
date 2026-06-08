"""Protocol interface for WhatsApp / messaging backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseMessagingClient(Protocol):
    """Minimal surface required from any messaging backend."""

    def send_text(self, jid: str, text: str, *, add_prefix: bool = True) -> bool:
        """Send a text message. Returns True on success."""
        ...

    def is_bot_message(self, text: str) -> bool:
        """Return True if the text was sent by this bot (echo guard)."""
        ...

    def format_reply(self, text: str) -> str:
        """Apply bot-prefix formatting to outgoing text."""
        ...
