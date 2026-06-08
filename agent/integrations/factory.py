"""Return the active integration client based on EVI_ORCHESTRATOR."""

from __future__ import annotations

import os
from functools import lru_cache

from integrations.base import BaseIntegrationClient


@lru_cache(maxsize=1)
def get_integration() -> BaseIntegrationClient:
    """Factory: returns a singleton integration client for the configured provider."""
    provider = os.getenv("EVI_ORCHESTRATOR", "windmill").strip().lower()

    if provider == "windmill":
        from integrations.windmill import WindmillClient
        return WindmillClient()

    raise ValueError(
        f"Unknown EVI_ORCHESTRATOR='{provider}'. Supported: windmill"
    )
