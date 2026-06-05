"""Windmill script: schedule_event — Google Calendar via gcal OAuth resource."""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict


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


def _resolve_calendar_id(access_token: str, calendar_id: str) -> str:
    cid = (calendar_id or "primary").strip()
    if cid == "primary" or "@" in cid or cid.endswith(".google.com"):
        return cid
    req = urllib.request.Request(
        "https://www.googleapis.com/calendar/v3/users/me/calendarList",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            items = json.loads(resp.read().decode("utf-8")).get("items", [])
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise ValueError(
                f"Cannot list calendars to resolve '{cid}' (missing calendar.readonly scope). "
                "Set WINDMILL_CALENDAR_ID to the full Calendar ID from Google: "
                "Calendar → EVI → Settings → Integrate calendar → Calendar ID "
                "(format …@group.calendar.google.com), or use primary."
            ) from e
        raise
    for item in items:
        if item.get("summary") == cid or item.get("id") == cid:
            return item["id"]
    names = [i.get("summary") for i in items if i.get("summary")]
    raise ValueError(
        f"Calendar '{cid}' not found. Available: {', '.join(names[:20])}"
    )


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


def _wall_clock(iso_time: str) -> str:
    t = (iso_time or "").strip()
    if t.endswith("Z"):
        t = t[:-1]
    elif len(t) > 19 and t[19] in "+-":
        t = t[:19]
    if len(t) == 16 and "T" in t:
        t += ":00"
    return t


def main(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    gcal: str = "gcal",
    calendar_id: str = "primary",
    timezone: str = "America/Sao_Paulo",
):
    token = _access_token(gcal)
    resolved_calendar = _resolve_calendar_id(token, calendar_id)
    tz = (timezone or "America/Sao_Paulo").strip() or "America/Sao_Paulo"
    start_local = _wall_clock(start_time)
    end_local = _wall_clock(end_time)
    body: Dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start_local, "timeZone": tz},
        "end": {"dateTime": end_local, "timeZone": tz},
    }
    if description:
        body["description"] = description

    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/{resolved_calendar}/events"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8", errors="replace")
        return {
            "status": "error",
            "action": "schedule_event",
            "http_status": status,
            "detail": raw[:500],
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
        }

    if status >= 400:
        return {
            "status": "error",
            "action": "schedule_event",
            "http_status": status,
            "detail": raw[:500],
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
        }

    data = json.loads(raw)
    return {
        "status": "created",
        "action": "schedule_event",
        "event_id": data.get("id"),
        "html_link": data.get("htmlLink"),
        "calendar_id": resolved_calendar,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
    }
