"""Return the active messaging client based on EVI_WHATSAPP_PROVIDER."""

from __future__ import annotations

import os
from functools import lru_cache

from messaging.base import BaseMessagingClient


@lru_cache(maxsize=1)
def get_messaging() -> BaseMessagingClient:
    """Factory: returns a singleton messaging client for the configured provider."""
    provider = os.getenv("EVI_WHATSAPP_PROVIDER", "evolution").strip().lower()

    if provider == "evolution":
        from messaging.evolution import EvolutionClient
        return EvolutionClient()

    raise ValueError(
        f"Unknown EVI_WHATSAPP_PROVIDER='{provider}'. Supported: evolution"
    )
