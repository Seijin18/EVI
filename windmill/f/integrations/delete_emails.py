"""Windmill script: delete_emails — move Gmail messages to trash via OAuth resource."""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List


def _fetch_resource(path: str) -> Any:
    base = os.environ.get("BASE_INTERNAL_URL", "http://localhost:8000").rstrip("/")
    workspace = os.environ["WM_WORKSPACE"]
    token = os.environ["WM_TOKEN"]
    resource_path = path.strip().lstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    for suffix in (
        f"/resources/get_value_interpolated/{resource_path}",
        f"/resources/get/{resource_path}",
    ):
        url = f"{base}/api/w/{workspace}{suffix}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        if isinstance(data, dict) and "value" in data:
            value = data["value"]
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return {"token": value}
            return value
        return data
    raise ValueError(f"resource not found: {resource_path}")


def _access_token(resource: Any) -> str:
    if isinstance(resource, str):
        resource = _fetch_resource(resource)
    if not isinstance(resource, dict):
        raise ValueError("gmail resource must be a dict or Windmill resource path")
    for key in ("token", "access_token", "accessToken"):
        val = resource.get(key)
        if isinstance(val, str) and val:
            return val
    oauth = resource.get("oauth") or resource.get("oauth2")
    if isinstance(oauth, dict):
        for key in ("access_token", "token"):
            val = oauth.get(key)
            if isinstance(val, str) and val:
                return val
    raise ValueError("No access token in gmail resource")


def _gmail_post(token: str, path: str) -> Dict[str, Any]:
    url = f"https://gmail.googleapis.com/gmail/v1/users/me{path}"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body.strip() else {}


def main(message_ids: List[str], gmail: str = "gmail"):
    if not message_ids:
        return {
            "status": "error",
            "action": "delete_emails",
            "detail": "message_ids required",
            "deleted": 0,
        }
    token = _access_token(gmail)
    deleted = 0
    errors: List[str] = []
    for mid in message_ids[:25]:
        mid = str(mid).strip()
        if not mid:
            continue
        try:
            _gmail_post(token, f"/messages/{mid}/trash")
            deleted += 1
        except urllib.error.HTTPError as e:
            errors.append(f"{mid}: HTTP {e.code}")
        except Exception as exc:
            errors.append(f"{mid}: {exc}")

    if deleted == 0 and errors:
        return {
            "status": "error",
            "action": "delete_emails",
            "detail": "; ".join(errors)[:500],
            "deleted": 0,
        }
    out: Dict[str, Any] = {
        "status": "ok",
        "action": "delete_emails",
        "deleted": deleted,
    }
    if errors:
        out["warnings"] = errors[:5]
    return out
