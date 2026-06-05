"""Windmill script: receive Telegram update, forward to EVI agent-api."""

import json
import os
import urllib.error
import urllib.request


def _normalize_update(update: dict | None, **kwargs) -> dict:
    """Telegram setWebhook sends update at JSON root; Windmill UI tests wrap in 'update'."""
    if update and isinstance(update, dict) and update.get("message"):
        return update
    if update and isinstance(update, dict) and "update" in update:
        inner = update.get("update")
        if isinstance(inner, dict):
            return inner
    if kwargs.get("message"):
        return dict(kwargs)
    if update and isinstance(update, dict):
        return update
    raise ValueError("missing Telegram update (expected message or update object)")


def main(update: dict | None = None, **kwargs):
    payload = _normalize_update(update, **kwargs)
    api_url = os.environ.get("EVI_AGENT_URL", "http://agent-api:8000/webhooks/telegram")
    api_key = os.environ.get("EVI_API_KEY", "")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(api_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {"ok": True}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"EVI telegram webhook HTTP {e.code}: {detail}") from e
