"""POST JSON payloads to Windmill HTTP triggers (replaces n8n webhooks)."""

import os
from typing import Any, Dict, Optional

import requests


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
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        limit = 2000 if wait_result else 500
        return response.text[:limit] if response.text else "ok"
    except requests.HTTPError as e:
        detail = ""
        if e.response is not None and e.response.text:
            detail = f" {e.response.text[:1500]}"
        return f"Windmill request failed: {e}{detail}"
    except Exception as e:
        return f"Windmill request failed: {e}"
