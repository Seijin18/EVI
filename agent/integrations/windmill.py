"""Windmill HTTP-trigger backend (current default)."""

from __future__ import annotations

import os

from tools.windmill_client import post_windmill

_OPERATION_MAP = {
    "schedule_event": (
        "WINDMILL_WEBHOOK_CALENDAR",
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/schedule_event",
    ),
    "list_events": (
        "WINDMILL_WEBHOOK_LIST_EVENTS",
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/list_events",
    ),
    "create_task": (
        "WINDMILL_WEBHOOK_TASKS",
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/create_task",
    ),
    "summarize_inbox": (
        "WINDMILL_WEBHOOK_EMAIL",
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/summarize_inbox",
    ),
}


class WindmillClient:
    """Delegates all operations to Windmill HTTP webhooks via post_windmill."""

    def post(
        self,
        operation: str,
        payload: dict,
        *,
        timeout: int = 60,
        wait_result: bool = True,
    ) -> str:
        if operation not in _OPERATION_MAP:
            return f"Unknown Windmill operation: {operation}"
        env_var, default_url = _OPERATION_MAP[operation]
        return post_windmill(env_var, payload, default_url, timeout=timeout, wait_result=wait_result)
