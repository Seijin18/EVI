"""One place to record non-fatal failures instead of swallowing them.

Optional side effects (contact memory, graph sync, notifications, profile
updates) must never break a request — but they were failing invisibly, so the
observed behaviour was "nothing happened, no trace". `soft_fail` keeps them
non-fatal and makes them greppable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("evi.softfail")


def soft_fail(context: str, exc: BaseException, *, detail: str = "") -> None:
    """Log a swallowed exception under a stable, greppable context label.

    `context` is a dotted path like "main.evolution_webhook.graph_sync" — stable
    across refactors so log searches keep working.
    """
    suffix = f" ({detail})" if detail else ""
    logger.warning(
        "soft-fail %s%s: %s: %s",
        context,
        suffix,
        type(exc).__name__,
        str(exc)[:200],
    )
