"""Feature flag for legacy direct-handler bypass (debug only)."""

from __future__ import annotations

import os


def direct_handlers_enabled() -> bool:
    return os.getenv("EVI_DIRECT_HANDLERS", "false").lower() in (
        "1",
        "true",
        "yes",
    )
