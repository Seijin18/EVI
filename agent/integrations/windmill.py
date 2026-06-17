"""Windmill HTTP-trigger backend (current default orchestration provider)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict

import requests

_RETRYABLE_STATUS = frozenset({401, 422})

_OPERATION_MAP: dict[str, tuple[str, str]] = {
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
    "delete_emails": (
        "WINDMILL_WEBHOOK_EMAIL_DELETE",
        "http://windmill-server:8000/api/w/evi/jobs/run/p/f/integrations/delete_emails",
    ),
}


def _windmill_post(
    env_var: str,
    payload: Dict[str, Any],
    default_url: str,
    *,
    timeout: int = 30,
    wait_result: bool = False,
) -> str:
    """Core HTTP POST to a Windmill webhook with OAuth retry and wait_result support."""
    url = os.getenv(env_var, default_url)
    if wait_result:
        url = url.replace("/jobs/run/p/", "/jobs/run_wait_result/p/")
    if not url:
        return f"Missing {env_var}"

    headers: Dict[str, str] = {}
    token = os.getenv("WINDMILL_TOKEN", "").strip()
    if token and "token=" not in url:
        headers["Authorization"] = f"Bearer {token}"

    attempts = max(1, int(os.getenv("EVI_WINDMILL_RETRY_ATTEMPTS", "2")))
    delay = float(os.getenv("EVI_WINDMILL_RETRY_DELAY_SEC", "2"))
    last_err: Exception | None = None

    for attempt in range(attempts):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            limit = 2000 if wait_result else 500
            return response.text[:limit] if response.text else "ok"
        except requests.HTTPError as e:
            last_err = e
            status = e.response.status_code if e.response is not None else 0
            if attempt + 1 < attempts and status in _RETRYABLE_STATUS:
                time.sleep(delay)
                continue
            detail = ""
            if e.response is not None and e.response.text:
                detail = f" {e.response.text[:1500]}"
            hint = ""
            if status in _RETRYABLE_STATUS:
                hint = " (OAuth/token Windmill — tente novamente se persistir)"
            return f"Windmill request failed: {e}{detail}{hint}"
        except Exception as e:
            last_err = e
            if attempt + 1 < attempts:
                time.sleep(delay)
                continue
            return f"Windmill request failed: {e}"

    return f"Windmill request failed: {last_err}"


class WindmillClient:
    """Delegates all operations to Windmill HTTP webhooks."""

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
        return _windmill_post(
            env_var,
            payload,
            default_url,
            timeout=timeout,
            wait_result=wait_result,
        )
