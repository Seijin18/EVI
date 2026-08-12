"""Protocol interface for WhatsApp / messaging backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from services.send_result import SendResult


@runtime_checkable
class BaseMessagingClient(Protocol):
    """Minimal surface required from any messaging backend."""

    def send_text(self, jid: str, text: str, *, add_prefix: bool = True) -> SendResult:
        """Send a text message.

        Returns a truthy-on-success SendResult carrying a failure reason.
        Must never raise — a failed delivery is reported, not propagated.
        """
        ...

    def is_bot_message(self, text: str) -> bool:
        """Return True if the text was sent by this bot (echo guard)."""
        ...

    def format_reply(self, text: str) -> str:
        """Apply bot-prefix formatting to outgoing text."""
        ...
