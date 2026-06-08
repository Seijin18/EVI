"""Evolution API client — thin shim over messaging.evolution (backward compat)."""

from __future__ import annotations

from messaging.evolution import EvolutionClient as _EvolutionClient, reply_prefix

_client = _EvolutionClient()


def is_evi_bot_message(text: str) -> bool:
    return _client.is_bot_message(text)


def format_evi_whatsapp(text: str) -> str:
    return _client.format_reply(text)


def send_whatsapp_text(jid: str, text: str, *, add_prefix: bool = True) -> bool:
    return _client.send_text(jid, text, add_prefix=add_prefix)


__all__ = ["is_evi_bot_message", "format_evi_whatsapp", "send_whatsapp_text", "reply_prefix"]
