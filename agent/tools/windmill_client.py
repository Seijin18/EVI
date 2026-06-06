"""POST JSON payloads to Windmill HTTP triggers (replaces n8n webhooks)."""

import os
import time
from typing import Any, Dict

import requests

# Windmill may return 401/422 while OAuth resource tokens refresh on first access.
_RETRYABLE_STATUS = frozenset({401, 422})


def post_windmill(
    env_var: str,
    payload: Dict[str, Any],
    default_url: str,
    timeout: int = 30,
    wait_result: bool = False,
) -> str:
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
            response = requests.post(
                url, json=payload, headers=headers, timeout=timeout
            )
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
