"""Windmill script: list_tasks — open Google Tasks via gtasks OAuth resource."""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List
from urllib.parse import quote, urlencode


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
        raise ValueError("gtasks resource must be a dict or Windmill resource path")
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
    raise ValueError("No access token in gtasks resource")


def _due_label(due: str | None) -> str:
    if not due:
        return "sem prazo"
    return due[:10] if "T" in due else due


def main(
    gtasks: str = "gtasks",
    tasklist_id: str = "@default",
    max_results: int = 25,
    show_completed: bool = False,
):
    token = _access_token(gtasks)
    list_id = quote(tasklist_id, safe="@")
    params = urlencode(
        {
            "maxResults": max(1, min(int(max_results), 100)),
            "showCompleted": "true" if show_completed else "false",
            "showHidden": "false",
        }
    )
    url = f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks?{params}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {
            "status": "error",
            "action": "list_tasks",
            "http_status": e.code,
            "detail": e.read().decode("utf-8", errors="replace")[:500],
        }

    items: List[Dict[str, Any]] = []
    for row in raw.get("items") or []:
        if row.get("status") == "completed" and not show_completed:
            continue
        items.append(
            {
                "id": row.get("id") or "",
                "title": row.get("title") or "(sem título)",
                "due": _due_label(row.get("due")),
                "status": row.get("status") or "needsAction",
            }
        )

    return {
        "status": "ok",
        "action": "list_tasks",
        "count": len(items),
        "tasks": items,
    }
