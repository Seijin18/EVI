"""POST JSON payloads to Windmill HTTP triggers (replaces n8n webhooks)."""

import os
from typing import Any, Dict, Optional

import requests


def post_windmill(
    env_var: str,
    payload: Dict[str, Any],
    default_url: str,
    timeout: int = 30,
) -> str:
    url = os.getenv(env_var, default_url)
    if not url:
        return f"Missing {env_var}"
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.text[:500] if response.text else "ok"
    except Exception as e:
        return f"Windmill request failed: {e}"
