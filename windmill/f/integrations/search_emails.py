"""Windmill script: search_emails — READ-ONLY Gmail search (GET only, never trashes)."""

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


def _gmail_get(token: str, path: str) -> Dict[str, Any]:
    url = f"https://gmail.googleapis.com/gmail/v1/users/me{path}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(q: str, max_messages: int = 25, gmail: str = "gmail"):
    query = (q or "").strip()
    if not query:
        return {
            "status": "error",
            "action": "search_emails",
            "detail": "q (Gmail search query) required",
            "count": 0,
            "messages": [],
        }
    token = _access_token(gmail)
    limit = max(1, min(int(max_messages), 50))
    from urllib.parse import quote

    try:
        listing = _gmail_get(token, f"/messages?q={quote(query)}&maxResults={limit}")
    except urllib.error.HTTPError as e:
        return {
            "status": "error",
            "action": "search_emails",
            "http_status": e.code,
            "detail": e.read().decode("utf-8", errors="replace")[:500],
            "count": 0,
            "messages": [],
        }

    found: List[Dict[str, Any]] = []
    for m in listing.get("messages", []):
        mid = m.get("id")
        if not mid:
            continue
        try:
            msg = _gmail_get(
                token,
                f"/messages/{mid}?format=metadata&metadataHeaders=Subject&metadataHeaders=From",
            )
        except urllib.error.HTTPError:
            found.append({"id": mid, "subject": "", "from": ""})
            continue
        hdrs = {
            h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])
        }
        found.append(
            {
                "id": mid,
                "subject": hdrs.get("Subject", "(no subject)"),
                "from": hdrs.get("From", ""),
            }
        )
    return {
        "status": "ok",
        "action": "search_emails",
        "count": len(found),
        "messages": found,
        "q": query,
    }
