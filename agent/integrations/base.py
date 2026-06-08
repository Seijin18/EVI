"""Protocol interface for integration / orchestration backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseIntegrationClient(Protocol):
    """Minimal surface for calendar, tasks, email, and event-listing operations."""

    def post(
        self,
        operation: str,
        payload: dict,
        *,
        timeout: int = 60,
        wait_result: bool = True,
    ) -> str:
        """Execute an operation and return a string result."""
        ...
