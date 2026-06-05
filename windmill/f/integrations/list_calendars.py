"""List Google calendars (summary + id) for configuring WINDMILL_CALENDAR_ID."""

import json
import urllib.error
import urllib.request
from typing import Any


def _access_token(resource: Any) -> str:
    if isinstance(resource, dict):
        for key in ("access_token", "token", "accessToken"):
            val = resource.get(key)
            if isinstance(val, str) and val:
                return val
        oauth = resource.get("oauth") or resource.get("oauth2")
        if isinstance(oauth, dict):
            for key in ("access_token", "token"):
                val = oauth.get(key)
                if isinstance(val, str) and val:
                    return val
    raise ValueError("Pass gcal as $res:u/.../beneficial_gcal in Run args")


def main(gcal: Any):
    token = _access_token(gcal)
    req = urllib.request.Request(
        "https://www.googleapis.com/calendar/v3/users/me/calendarList",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            items = json.loads(resp.read().decode("utf-8")).get("items", [])
    except urllib.error.HTTPError as e:
        return {
            "status": "error",
            "http_status": e.code,
            "hint": "Add calendar.readonly scope to gcal OAuth and reconnect, "
            "or copy Calendar ID from Google Calendar → EVI → Settings.",
            "detail": e.read().decode("utf-8", errors="replace")[:400],
        }
    return {
        "status": "ok",
        "calendars": [
            {"summary": i.get("summary"), "id": i.get("id")} for i in items
        ],
    }
