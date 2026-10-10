"""Stateful fake of the Google APIs, for the EVI simulation harness.

Implements ONLY the subset the real Windmill scripts in
``windmill/f/integrations/*.py`` call (see ``ENDPOINTS``). Anything else answers
500 with the URL in the body, so a scenario fails loudly instead of passing by
accident. State lives in memory and is seeded per scenario.

Core: ``FakeGoogle.handle(method, url, headers, body) -> (status, body, headers)``
(plain Python, usable in-process by a fake ``urlopen``), plus ``seed`` / ``state``
/ ``reset``. ``build_app`` exposes it over HTTP with ``/_sim/*`` control endpoints.

Seed format (all keys optional)::

    {"calendar": [{"summary", "start", "end", "description"?, "id"?}],
     "tasks":    [{"title", "due"?, "status"?, "notes"?, "id"?}],
     "gmail":    [{"id"?, "from", "subject", "snippet", "labels": [...], "date"?}],
     "calendars": [{"id", "summary"}]}   # default: one primary calendar

``start``/``end`` are ISO strings (naive ones are read in EVI_TIMEZONE, default
America/Sao_Paulo); a date-only string makes an all-day event.

``state()`` returns the same lists (live, minus trashed mail) plus tracking:
``created`` {"calendar": [...], "tasks": [...]} for items inserted via the API,
``trashed`` / ``deleted`` (same ids: the scripts' "delete" is Gmail trash).

Gmail ``q`` subset: ``category:X`` (label CATEGORY_X), ``label:X``, ``in:inbox``,
``is:unread|read``, ``from:``, ``subject:``, ``newer_than:Nd|Nh|Nm``,
``older_than:...``, a leading ``-`` negates, quoted phrases, and bare words
(substring of subject/snippet/from). Any other ``operator:value`` -> 500.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shlex
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from zoneinfo import ZoneInfo

Response = tuple[int, bytes, dict[str, str]]

DEFAULT_TZ = "America/Sao_Paulo"
CAL_HOST = "www.googleapis.com"
TASKS_HOST = "tasks.googleapis.com"
GMAIL_HOST = "gmail.googleapis.com"
KNOWN_HOSTS = {CAL_HOST, TASKS_HOST, GMAIL_HOST}

# method + path pattern of everything implemented (for docs / task 2.2).
ENDPOINTS = [
    ("GET", "/calendar/v3/users/me/calendarList"),
    ("GET", "/calendar/v3/calendars/{calId}/events"),
    ("POST", "/calendar/v3/calendars/{calId}/events"),
    ("GET", "/tasks/v1/lists/{listId}/tasks"),
    ("POST", "/tasks/v1/lists/{listId}/tasks"),
    ("GET", "/gmail/v1/users/me/messages"),
    ("GET", "/gmail/v1/users/me/messages/{id}"),
    ("POST", "/gmail/v1/users/me/messages/{id}/trash"),
]


def _tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("EVI_TIMEZONE") or DEFAULT_TZ)


def _json(status: int, obj: Any) -> Response:
    return status, json.dumps(obj).encode(), {"Content-Type": "application/json"}


def _gerr(status: int, message: str) -> Response:
    return _json(status, {"error": {"code": status, "message": message}})


def _parse_dt(value: str, tz: ZoneInfo) -> datetime:
    v = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(v)
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def _is_date_only(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()))


class _Unsupported(Exception):
    pass


class FakeGoogle:
    def __init__(self) -> None:
        self.reset()

    # ------------------------------------------------------------- control
    def reset(self) -> None:
        self._calendars: list[dict] = [{"id": "primary@sim.local", "summary": "EVI", "primary": True}]
        self._events: list[dict] = []
        self._tasks: list[dict] = []
        self._mail: list[dict] = []
        self._created: dict[str, list[dict]] = {"calendar": [], "tasks": []}
        self._trashed: list[str] = []
        self._seq = {"evt": 0, "task": 0, "msg": 0}

    def _next(self, kind: str) -> str:
        self._seq[kind] += 1
        return f"{kind}-{self._seq[kind]}"

    def seed(self, data: dict) -> None:
        """Replace the whole state with the scenario's seed."""
        self.reset()
        tz = _tz()
        if data.get("calendars"):
            self._calendars = [dict(c) for c in data["calendars"]]
        for e in data.get("calendar") or []:
            self._events.append(self._make_event(e, tz))
        for t in data.get("tasks") or []:
            self._tasks.append(self._make_task(t))
        for m in data.get("gmail") or []:
            self._mail.append(self._make_mail(m, tz))

    def state(self) -> dict:
        tz = _tz()
        return copy.deepcopy(
            {
                "calendars": self._calendars,
                "calendar": [self._event_view(e) for e in self._events],
                "tasks": self._tasks,
                "gmail": [m for m in self._mail if "TRASH" not in m["labelIds"]],
                "trash": [m for m in self._mail if "TRASH" in m["labelIds"]],
                "created": self._created,
                "trashed": self._trashed,
                "deleted": list(self._trashed),
                "timezone": str(tz),
            }
        )

    # --------------------------------------------------------------- build
    def _make_event(self, e: dict, tz: ZoneInfo, src_tz: str | None = None) -> dict:
        def side(v: str) -> dict:
            if _is_date_only(v):
                return {"date": v}
            return {"dateTime": _parse_dt(v, tz).isoformat(), "timeZone": src_tz or str(tz)}

        eid = e.get("id") or self._next("evt")
        ev = {
            "id": eid,
            "summary": e.get("summary") or "",
            "start": side(e["start"]),
            "end": side(e["end"]),
            "htmlLink": f"https://calendar.sim.local/event?eid={eid}",
            "status": "confirmed",
        }
        if e.get("description"):
            ev["description"] = e["description"]
        return ev

    def _event_view(self, e: dict) -> dict:
        # flat form for scenario assertions + the raw API shape under "raw"
        return {
            "id": e["id"],
            "summary": e["summary"],
            "start": e["start"].get("dateTime") or e["start"].get("date"),
            "end": e["end"].get("dateTime") or e["end"].get("date"),
            "description": e.get("description", ""),
            "raw": e,
        }

    def _make_task(self, t: dict) -> dict:
        due = t.get("due")
        if due and _is_date_only(due):
            due = f"{due}T00:00:00.000Z"
        task = {
            "id": t.get("id") or self._next("task"),
            "title": t.get("title") or "",
            "status": t.get("status") or "needsAction",
        }
        if due:
            task["due"] = due
        if t.get("notes"):
            task["notes"] = t["notes"]
        return task

    def _make_mail(self, m: dict, tz: ZoneInfo) -> dict:
        date_s = m.get("date")
        when = _parse_dt(date_s, tz) if date_s else datetime.now(tz)
        return {
            "id": m.get("id") or self._next("msg"),
            "from": m.get("from", ""),
            "subject": m.get("subject", ""),
            "snippet": m.get("snippet", ""),
            "labelIds": list(m.get("labels") if m.get("labels") is not None else ["INBOX", "UNREAD"]),
            "date": when.isoformat(),
        }

    # ------------------------------------------------------------- routing
    def handle(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        """Dispatch one Google API call. ``url`` may be absolute or path+query."""
        method = method.upper()
        parts = urlsplit(url)
        path = parts.path
        query = {k: v for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        hdrs = {k.lower(): v for k, v in (headers or {}).items()}
        try:
            if parts.netloc and parts.netloc not in KNOWN_HOSTS:
                raise _Unsupported
            if not hdrs.get("authorization", "").startswith("Bearer "):
                return _gerr(401, "Missing bearer token")
            payload: dict = {}
            if body and body.strip():
                try:
                    payload = json.loads(body)
                except ValueError:
                    return _gerr(400, "Invalid JSON body")
            r = self._route(method, path, query, payload)
            if r is not None:
                return r
        except _Unsupported:
            pass
        return (
            500,
            f"fake-google: unimplemented endpoint {method} {url}".encode(),
            {"Content-Type": "text/plain"},
        )

    def _route(self, method: str, path: str, q: dict, body: dict) -> Response | None:
        p = path.rstrip("/")
        if p == "/calendar/v3/users/me/calendarList" and method == "GET":
            return _json(200, {"kind": "calendar#calendarList", "items": copy.deepcopy(self._calendars)})
        m = re.fullmatch(r"/calendar/v3/calendars/([^/]+)/events", p)
        if m:
            cal = self._resolve_calendar(unquote(m.group(1)))
            if cal is None:
                return _gerr(404, "Not Found")
            if method == "GET":
                return self._events_list(cal, q)
            if method == "POST":
                return self._events_insert(body)
            return None
        m = re.fullmatch(r"/tasks/v1/lists/([^/]+)/tasks", p)
        if m:
            if method == "GET":
                return self._tasks_list(q)
            if method == "POST":
                return self._tasks_insert(body)
            return None
        if p == "/gmail/v1/users/me/messages" and method == "GET":
            return self._mail_list(q)
        m = re.fullmatch(r"/gmail/v1/users/me/messages/([^/]+)", p)
        if m and method == "GET":
            return self._mail_get(unquote(m.group(1)), q)
        m = re.fullmatch(r"/gmail/v1/users/me/messages/([^/]+)/trash", p)
        if m and method == "POST":
            return self._mail_trash(unquote(m.group(1)))
        return None

    # ------------------------------------------------------------ calendar
    def _resolve_calendar(self, cid: str) -> dict | None:
        if cid == "primary":
            return next((c for c in self._calendars if c.get("primary")), self._calendars[0])
        return next((c for c in self._calendars if c["id"] == cid), None)

    def _events_list(self, cal: dict, q: dict) -> Response:
        tz = _tz()
        tmin = _parse_dt(q["timeMin"][0], tz) if q.get("timeMin") else None
        tmax = _parse_dt(q["timeMax"][0], tz) if q.get("timeMax") else None
        limit = int(q["maxResults"][0]) if q.get("maxResults") else 250

        def bounds(e: dict) -> tuple[datetime, datetime]:
            def one(side: dict) -> datetime:
                if "date" in side:
                    return datetime.combine(date.fromisoformat(side["date"]), datetime.min.time(), tzinfo=tz)
                return _parse_dt(side["dateTime"], tz)

            return one(e["start"]), one(e["end"])

        rows = []
        for e in self._events:
            s, en = bounds(e)
            if tmin and en <= tmin:
                continue
            if tmax and s >= tmax:
                continue
            rows.append((s, e))
        rows.sort(key=lambda r: r[0])
        items = [copy.deepcopy(e) for _, e in rows[:limit]]
        return _json(200, {"kind": "calendar#events", "summary": cal["summary"], "items": items})

    def _events_insert(self, body: dict) -> Response:
        try:
            tz = _tz()
            st, en = body["start"], body["end"]
            src_tz = st.get("timeZone")
            zone = ZoneInfo(src_tz) if src_tz else tz
            norm = {
                "summary": body.get("summary", ""),
                "description": body.get("description", ""),
                "start": st.get("dateTime") or st["date"],
                "end": en.get("dateTime") or en["date"],
            }
            ev = self._make_event(norm, zone, src_tz)
        except (KeyError, ValueError):
            return _gerr(400, "Invalid start/end")
        self._events.append(ev)
        self._created["calendar"].append(self._event_view(ev) | {"request": body})
        return _json(200, copy.deepcopy(ev))

    # --------------------------------------------------------------- tasks
    def _tasks_list(self, q: dict) -> Response:
        show_completed = (q.get("showCompleted") or ["true"])[0] == "true"
        limit = int(q["maxResults"][0]) if q.get("maxResults") else 20
        rows = [t for t in self._tasks if show_completed or t["status"] != "completed"]
        return _json(200, {"kind": "tasks#tasks", "items": copy.deepcopy(rows[:limit])})

    def _tasks_insert(self, body: dict) -> Response:
        if not body.get("title"):
            return _gerr(400, "title required")
        task = self._make_task(body)
        self._tasks.append(task)
        self._created["tasks"].append(copy.deepcopy(task))
        return _json(200, copy.deepcopy(task))

    # --------------------------------------------------------------- gmail
    def _mail_list(self, q: dict) -> Response:
        limit = int(q["maxResults"][0]) if q.get("maxResults") else 100
        want_labels = q.get("labelIds") or []
        rows = [
            m
            for m in self._mail
            if all(lb in m["labelIds"] for lb in want_labels)
            and ("TRASH" in m["labelIds"]) == ("TRASH" in want_labels)
        ]
        if q.get("q") and q["q"][0].strip():
            rows = [m for m in rows if self._match(m, q["q"][0])]
        rows.sort(key=lambda m: m["date"], reverse=True)
        rows = rows[:limit]
        out: dict[str, Any] = {"resultSizeEstimate": len(rows)}
        if rows:
            out["messages"] = [{"id": m["id"], "threadId": m["id"]} for m in rows]
        return _json(200, out)

    def _match(self, m: dict, query: str) -> bool:
        try:
            tokens = shlex.split(query)
        except ValueError:
            tokens = query.split()
        now = datetime.now(_tz())
        when = datetime.fromisoformat(m["date"])
        for tok in tokens:
            neg = tok.startswith("-") and len(tok) > 1
            t = tok[1:] if neg else tok
            op, _, val = t.partition(":")
            op = op.lower()
            if not _ or " " in op:
                ok = t.lower() in f"{m['subject']} {m['snippet']} {m['from']}".lower()
            elif op == "category":
                ok = f"CATEGORY_{val.upper()}" in m["labelIds"]
            elif op == "label":
                ok = val.upper() in m["labelIds"]
            elif op == "in":
                ok = val.upper() in m["labelIds"]
            elif op == "is":
                v = val.lower()
                if v == "unread":
                    ok = "UNREAD" in m["labelIds"]
                elif v == "read":
                    ok = "UNREAD" not in m["labelIds"]
                else:
                    raise _Unsupported
            elif op == "from":
                ok = val.lower() in m["from"].lower()
            elif op == "subject":
                ok = val.lower() in m["subject"].lower()
            elif op in ("newer_than", "older_than"):
                mm = re.fullmatch(r"(\d+)([dhm])", val)
                if not mm:
                    raise _Unsupported
                n, unit = int(mm.group(1)), mm.group(2)
                delta = {"d": timedelta(days=n), "h": timedelta(hours=n), "m": timedelta(minutes=n)}[unit]
                recent = when >= now - delta
                ok = recent if op == "newer_than" else not recent
            else:
                raise _Unsupported
            if ok == neg:
                return False
        return True

    def _find_mail(self, mid: str) -> dict | None:
        return next((m for m in self._mail if m["id"] == mid), None)

    def _mail_view(self, m: dict, fmt: str, wanted: list[str]) -> dict:
        out: dict[str, Any] = {
            "id": m["id"],
            "threadId": m["id"],
            "labelIds": list(m["labelIds"]),
            "snippet": m["snippet"],
        }
        if fmt in ("metadata", "full"):
            hdrs = [
                {"name": "From", "value": m["from"]},
                {"name": "Subject", "value": m["subject"]},
                {"name": "Date", "value": m["date"]},
            ]
            if wanted:
                hdrs = [h for h in hdrs if h["name"] in wanted]
            out["payload"] = {"headers": hdrs}
        return out

    def _mail_get(self, mid: str, q: dict) -> Response:
        m = self._find_mail(mid)
        if m is None:
            return _gerr(404, "Requested entity was not found.")
        fmt = (q.get("format") or ["full"])[0]
        return _json(200, self._mail_view(m, fmt, q.get("metadataHeaders") or []))

    def _mail_trash(self, mid: str) -> Response:
        m = self._find_mail(mid)
        if m is None:
            return _gerr(404, "Requested entity was not found.")
        if "TRASH" not in m["labelIds"]:
            m["labelIds"] = [lb for lb in m["labelIds"] if lb != "INBOX"] + ["TRASH"]
            self._trashed.append(mid)
        return _json(200, self._mail_view(m, "minimal", []))


def build_app(fake: FakeGoogle | None = None):
    """Starlette app: ``/_sim/seed|state|reset`` controls + all Google paths."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response as HttpResponse
    from starlette.routing import Route

    g = fake or FakeGoogle()

    async def seed(req: Request):
        g.seed(await req.json())
        return JSONResponse({"ok": True})

    async def state(_req: Request):
        return JSONResponse(g.state())

    async def reset(_req: Request):
        g.reset()
        return JSONResponse({"ok": True})

    async def google(req: Request):
        url = req.url.path + (f"?{req.url.query}" if req.url.query else "")
        status, body, hdrs = g.handle(req.method, url, dict(req.headers), await req.body())
        return HttpResponse(body, status_code=status, headers=hdrs)

    app = Starlette(
        routes=[
            Route("/_sim/seed", seed, methods=["POST"]),
            Route("/_sim/state", state, methods=["GET"]),
            Route("/_sim/reset", reset, methods=["POST"]),
            Route("/{path:path}", google, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        ]
    )
    app.state.fake_google = g
    return app
