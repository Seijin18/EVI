"""Windmill script: list_events — upcoming Google Calendar events via gcal OAuth."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict
from zoneinfo import ZoneInfo


def _fetch_gcal_resource(path: str) -> Any:
    base = os.environ.get("BASE_INTERNAL_URL", "http://localhost:8000").rstrip("/")
    workspace = os.environ["WM_WORKSPACE"]
    token = os.environ["WM_TOKEN"]
    resource_path = path.strip().lstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    endpoints = (
        f"{base}/api/w/{workspace}/resources/get_value_interpolated/{resource_path}",
        f"{base}/api/w/{workspace}/resources/get/{resource_path}",
    )
    last_err: urllib.error.HTTPError | None = None
    for url in endpoints:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
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
    if last_err:
        raise last_err
    raise ValueError(f"gcal resource not found: {resource_path}")


def _access_token(resource: Any) -> str:
    if isinstance(resource, str):
        resource = _fetch_gcal_resource(resource)
    if not isinstance(resource, dict):
        raise ValueError("gcal resource must be a dict or Windmill resource path")
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
    raise ValueError(
        "No access token in gcal resource — reconnect gcal in Windmill Resources"
    )


def _resolve_calendar_id(access_token: str, calendar_id: str) -> str:
    cid = (calendar_id or "primary").strip()
    if cid == "primary" or "@" in cid or cid.endswith(".google.com"):
        return cid
    req = urllib.request.Request(
        "https://www.googleapis.com/calendar/v3/users/me/calendarList",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        items = json.loads(resp.read().decode("utf-8")).get("items", [])
    for item in items:
        if item.get("summary") == cid or item.get("id") == cid:
            return item["id"]
    names = [i.get("summary") for i in items if i.get("summary")]
    raise ValueError(
        f"Calendar '{cid}' not found. Available: {', '.join(names[:20])}"
    )


def _event_start_label(item: Dict[str, Any], tz_name: str) -> str:
    start = item.get("start") or {}
    if start.get("date"):
        return start["date"]
    dt = start.get("dateTime") or ""
    if not dt:
        return "?"
    try:
        parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        local = parsed.astimezone(ZoneInfo(tz_name))
        return local.strftime("%d/%m %H:%M")
    except (ValueError, KeyError):
        return dt[:16].replace("T", " ")


def main(
    gcal: str = "gcal",
    calendar_id: str = "primary",
    days_ahead: int = 7,
    max_results: int = 25,
    timezone: str = "America/Sao_Paulo",
):
    token = _access_token(gcal)
    resolved_calendar = _resolve_calendar_id(token, calendar_id)
    tz_name = (timezone or "America/Sao_Paulo").strip() or "America/Sao_Paulo"
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=max(1, int(days_ahead)))).isoformat()
    params = urllib.parse.urlencode(
        {
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max(1, min(int(max_results), 50)),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
    )
    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/"
        f"{urllib.parse.quote(resolved_calendar, safe='')}/events?{params}"
    )
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return {
            "status": "error",
            "action": "list_events",
            "http_status": e.code,
            "detail": e.read().decode("utf-8", errors="replace")[:500],
        }

    items = json.loads(raw).get("items") or []
    events = [
        {
            "summary": i.get("summary") or "(sem título)",
            "start": _event_start_label(i, tz_name),
            "html_link": i.get("htmlLink") or "",
        }
        for i in items
    ]
    return {
        "status": "ok",
        "action": "list_events",
        "calendar_id": resolved_calendar,
        "timezone": tz_name,
        "count": len(events),
        "events": events,
    }
