"""Windmill script: list_contacts — Google address book (name + phones only).

Reads People API `people/me/connections` with the `gcontacts` OAuth resource
(scope contacts.readonly). Data minimisation: only `name` and `phones` leave
this script — no e-mail, address, photo, notes or metadata.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_URL = "https://people.googleapis.com/v1/people/me/connections"
_MAX_PAGES = 20


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
    raise ValueError("Pass gcontacts as $res:u/.../gcontacts in Run args")


def _fetch_page(token: str, page_token: str | None) -> dict:
    """One People API call; the single HTTP seam (tests monkeypatch it)."""
    params = {"personFields": "names,phoneNumbers", "pageSize": "1000"}
    if page_token:
        params["pageToken"] = page_token
    req = urllib.request.Request(
        f"{_URL}?{urllib.parse.urlencode(params)}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _entry(person: dict) -> dict | None:
    names = person.get("names") or []
    name = (names[0].get("displayName") or "").strip() if names else ""
    if not name:
        return None
    phones: list[str] = []
    for p in person.get("phoneNumbers") or []:
        value = (p.get("value") or "").strip()
        if value and value not in phones:
            phones.append(value)
    if not phones:
        return None
    return {"name": name, "phones": phones}


def main(gcontacts: Any):
    token = _access_token(gcontacts)
    out: list[dict] = []
    page_token: str | None = None
    for _ in range(_MAX_PAGES):
        try:
            data = _fetch_page(token, page_token)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {
                    "error": f"Google People API HTTP {e.code}: reconnect the gcontacts OAuth resource",
                    "reason": "oauth",
                }
            return {"error": f"Google People API HTTP {e.code}", "reason": "upstream_error"}
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"error": f"People API unreachable: {type(e).__name__}", "reason": "upstream_error"}
        for person in data.get("connections") or []:
            entry = _entry(person)
            if entry:
                out.append(entry)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out
