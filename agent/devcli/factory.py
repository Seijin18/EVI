"""Return the active dev-bridge CLI backend based on EVI_DEV_CLI."""

from __future__ import annotations

import os
from functools import lru_cache

from devcli.base import DevCliBackend

_SUPPORTED = ("claude",)


def resolve_dev_cli(name: str) -> DevCliBackend:
    """Uncached backend lookup — used for per-job --cli= overrides."""
    backend = (name or "").strip().lower()

    if backend == "claude":
        from devcli.claude_backend import ClaudeCliBackend

        return ClaudeCliBackend()

    raise ValueError(
        f"Unknown dev-bridge CLI '{backend}'. Supported: {', '.join(_SUPPORTED)}"
    )


@lru_cache(maxsize=1)
def get_dev_cli() -> DevCliBackend:
    """Factory: returns a singleton backend for the configured default (EVI_DEV_CLI)."""
    return resolve_dev_cli(os.getenv("EVI_DEV_CLI", "claude"))
