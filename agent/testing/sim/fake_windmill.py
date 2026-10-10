"""Fake Windmill for the EVI simulation harness.

Runs the REAL scripts in ``windmill/f/integrations/`` (not reimplementations):
for ``POST /api/w/<ws>/jobs/run_wait_result/p/f/integrations/<op>`` it imports
``<scripts_dir>/<op>.py``, swaps the ``urllib`` name inside that module for a
shim whose ``request.urlopen`` routes to a ``FakeGoogle`` (Google hosts) or to
the fake resources endpoint (``/api/w/<ws>/resources/get...``), runs
``main(**payload)`` and answers like Windmill does:

* script returned a value -> 200, JSON of the value;
* script raised          -> 500, ``{"error": {"name": "ExecutionErr", ...}}``.

``urllib.request.urlopen`` is never patched globally (only the script module's
own ``urllib`` global is replaced), so the fakes process can still do network.
Scripts run under a lock because they read ``WM_*`` / ``BASE_INTERNAL_URL`` from
``os.environ``, which is patched for the duration of the run.

Async webhook ``jobs/run/p/...`` is supported too: it runs the job and returns
the job id (201, JSON string); the result is served at
``GET /api/w/<ws>/jobs_u/completed/get_result[_maybe]/<id>``.

Args shaped ``$res:<path>`` / ``$var:<path>`` are resolved to the fake OAuth
resource dict before ``main`` (Windmill does the same for resource args).

Faults (``set_faults({op_or_"*": fault})``, per scenario ``faults:``):

* ``oauth_expired``   Google answers 401 invalid_grant to every API call, so the
                      script's own error path builds the envelope.
* ``timeout``         sleeps ``timeout_sleep_sec`` (default beyond the agent's
                      longest Windmill timeout, 180s) then answers 504.
* ``http_500``        Windmill answers 500 as for a failed job (script not run).
* ``malformed_body``  200 with a non-JSON body (script not run).

``calls`` logs ``{op, payload, status, result|fault, ...}`` per run.
"""

from __future__ import annotations

import importlib.util
import inspect
import io
import json
import os
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
import uuid
from email.message import Message
from pathlib import Path
from typing import Any, Callable

Response = tuple[int, bytes, dict[str, str]]

DEFAULT_SCRIPTS_DIR = "/windmill/f/integrations"
DEFAULT_TIMEOUT_SLEEP_SEC = 200.0  # agent's longest Windmill timeout is 180s
FAULTS = ("oauth_expired", "timeout", "http_500", "malformed_body")
FAKE_TOKEN = "sim-fake-access-token"
FAKE_BASE = "http://windmill-sim:8000"
FAKE_WORKSPACE = "evi"

_JSON = {"Content-Type": "application/json"}


def _json(status: int, obj: Any) -> Response:
    return status, json.dumps(obj).encode(), dict(_JSON)


def _wm_error(status: int, message: str, name: str = "ExecutionErr") -> Response:
    return _json(status, {"error": {"name": name, "message": message, "extra": None}})


class _UrlResp:
    """Minimal urlopen response (context manager with read/status/headers)."""

    def __init__(self, status: int, body: bytes, headers: dict[str, str]):
        self.status = self.code = status
        self._body = body
        self.headers = headers

    def read(self, *_a: Any) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "_UrlResp":
        return self

    def __exit__(self, *_a: Any) -> bool:
        return False


class FakeWindmill:
    def __init__(
        self,
        fake_google: Any,
        scripts_dir: str | None = None,
        *,
        timeout_sleep_sec: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
        workspace: str = FAKE_WORKSPACE,
    ) -> None:
        self.google = fake_google
        self.scripts_dir = Path(
            scripts_dir or os.environ.get("EVI_SIM_WINDMILL_SCRIPTS_DIR") or DEFAULT_SCRIPTS_DIR
        )
        if timeout_sleep_sec is None:
            timeout_sleep_sec = float(
                os.environ.get("EVI_SIM_WINDMILL_TIMEOUT_SLEEP_SEC", DEFAULT_TIMEOUT_SLEEP_SEC)
            )
        self.timeout_sleep_sec = timeout_sleep_sec
        self._sleep = sleep
        self.workspace = workspace
        self.calls: list[dict] = []
        self._faults: dict[str, str] = {}
        self._jobs: dict[str, Response] = {}
        self._lock = threading.Lock()  # serialises script runs (os.environ patch)

    # ------------------------------------------------------------- control
    def set_faults(self, faults: dict[str, str] | None) -> None:
        faults = dict(faults or {})
        for op, f in faults.items():
            if f not in FAULTS:
                raise ValueError(f"unknown fault {f!r} for {op!r}; expected one of {FAULTS}")
        self._faults = faults

    def clear_faults(self) -> None:
        self._faults = {}

    def reset(self) -> None:
        self.clear_faults()
        self.calls = []
        self._jobs = {}

    def _fault_for(self, op: str) -> str | None:
        return self._faults.get(op) or self._faults.get("*")

    # ------------------------------------------------------------- routing
    def handle(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Response:
        method = method.upper()
        parts = urllib.parse.urlsplit(path)
        p = parts.path.rstrip("/") or "/"
        ws = self.workspace

        m = self._match_job_path(p)
        if method == "POST" and m:
            op, wait = m
            return self._run_endpoint(op, wait, body)

        prefix = f"/api/w/{ws}/jobs_u/completed/get_result"
        for pre in (prefix + "_maybe/", prefix + "/"):
            if method == "GET" and p.startswith(pre):
                job = self._jobs.get(p[len(pre):])
                if job is None:
                    return _wm_error(404, "job not found", "NotFound")
                return job

        if method == "GET" and p.startswith(f"/api/w/{ws}/resources/get"):
            return self._resource(p)
        if method == "GET" and p in ("/", "/api/version"):
            return _json(200, "CE v1.0.0-sim") if p == "/api/version" else (200, b"ok", {})
        return _wm_error(404, f"fake-windmill: unimplemented endpoint {method} {p}", "NotFound")

    def _match_job_path(self, p: str) -> tuple[str, bool] | None:
        for wait, seg in ((True, "run_wait_result"), (False, "run")):
            pre = f"/api/w/{self.workspace}/jobs/{seg}/p/f/integrations/"
            if p.startswith(pre):
                return p[len(pre):], wait
        return None

    def _resource(self, p: str) -> Response:
        kind, _, rpath = p.split("/resources/", 1)[1].partition("/")
        value = self._resource_value(rpath)
        if kind == "get_value_interpolated":
            return _json(200, value)
        return _json(200, {"path": rpath, "resource_type": "oauth", "value": value})

    @staticmethod
    def _resource_value(_path: str) -> dict:
        return {"token": FAKE_TOKEN}

    # ----------------------------------------------------------------- run
    def _run_endpoint(self, op: str, wait: bool, body: bytes | None) -> Response:
        try:
            payload = json.loads(body) if body and body.strip() else {}
            if not isinstance(payload, dict):
                raise ValueError("payload must be an object")
        except ValueError as e:
            return _wm_error(400, f"Invalid JSON body: {e}", "BadRequest")

        fault = self._fault_for(op)
        entry: dict[str, Any] = {"op": op, "payload": payload, "fault": fault, "wait": wait}
        self.calls.append(entry)

        if fault == "timeout":
            self._sleep(self.timeout_sleep_sec)
            resp = _wm_error(504, "Gateway Timeout", "TimeoutErr")
        elif fault == "http_500":
            resp = _wm_error(500, "Internal server error: job failed", "InternalErr")
        elif fault == "malformed_body":
            resp = (200, b"<html>bad gateway</html>", {"Content-Type": "text/html"})
        else:
            resp = self._execute(op, payload, entry, expired=(fault == "oauth_expired"))

        entry["status"] = resp[0]
        if fault is None and resp[0] == 200:
            try:
                entry["result"] = json.loads(resp[1])
            except ValueError:
                entry["result"] = resp[1].decode("utf-8", "replace")
        if wait:
            return resp
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = resp
        return 201, json.dumps(job_id).encode(), dict(_JSON)

    def _execute(self, op: str, payload: dict, entry: dict, *, expired: bool) -> Response:
        if not op.isidentifier():
            return _wm_error(404, f"Script not found: f/integrations/{op}", "NotFound")
        script = self.scripts_dir / f"{op}.py"
        if not script.is_file():
            return _wm_error(404, f"Script not found: f/integrations/{op}", "NotFound")

        args = {k: self._resolve_arg(v) for k, v in payload.items()}
        with self._lock:
            env = {
                "BASE_INTERNAL_URL": FAKE_BASE,
                "WM_WORKSPACE": self.workspace,
                "WM_TOKEN": "sim-wm-token",
            }
            saved = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                mod = self._load(script, op, expired)
                # Real Windmill only forwards args declared in main()'s signature
                # (extra payload keys such as the client's `action` are dropped).
                params = inspect.signature(mod.main).parameters
                if not any(p.kind is p.VAR_KEYWORD for p in params.values()):
                    args = {k: v for k, v in args.items() if k in params}
                result = mod.main(**args)
            except Exception as e:  # noqa: BLE001 - Windmill reports any script failure as 500
                entry["error"] = f"{type(e).__name__}: {e}"
                return _wm_error(500, f"Error during execution of the script: {type(e).__name__}: {e}")
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        try:
            return _json(200, result)
        except TypeError as e:
            entry["error"] = f"unserialisable result: {e}"
            return _wm_error(500, f"Result is not JSON serialisable: {e}")

    def _resolve_arg(self, v: Any) -> Any:
        if isinstance(v, str) and v.startswith(("$res:", "$var:")):
            return self._resource_value(v.split(":", 1)[1])
        return v

    # ----------------------------------------------------- script loading
    def _load(self, script: Path, op: str, expired: bool) -> types.ModuleType:
        spec = importlib.util.spec_from_file_location(f"_sim_wm_{op}", script)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "urllib"):
            mod.urllib = self._urllib_shim(expired)
        return mod

    def _urllib_shim(self, expired: bool) -> types.SimpleNamespace:
        def urlopen(req: Any, data: Any = None, timeout: Any = None, **_kw: Any) -> _UrlResp:
            if isinstance(req, str):
                url, method, hdrs, body = req, "GET" if data is None else "POST", {}, data
            else:
                url = req.full_url
                method = req.get_method()
                hdrs = dict(req.header_items())
                body = req.data if data is None else data
            status, rbody, rhdrs = self._route_url(method, url, hdrs, body, expired)
            if status >= 400:
                msg = Message()
                for k, v in rhdrs.items():
                    msg[k] = v
                raise urllib.error.HTTPError(url, status, f"HTTP {status}", msg, io.BytesIO(rbody))
            return _UrlResp(status, rbody, rhdrs)

        request = types.SimpleNamespace(
            urlopen=urlopen,
            Request=urllib.request.Request,
        )
        return types.SimpleNamespace(
            request=request, error=urllib.error, parse=urllib.parse
        )

    def _route_url(
        self, method: str, url: str, headers: dict, body: bytes | None, expired: bool
    ) -> Response:
        parts = urllib.parse.urlsplit(url)
        if parts.path.startswith(f"/api/w/{self.workspace}/resources/"):
            return self.handle(method, parts.path + (f"?{parts.query}" if parts.query else ""))
        if expired:
            return _json(
                401,
                {
                    "error": {
                        "code": 401,
                        "message": "Invalid Credentials (invalid_grant: Token has been expired or revoked.)",
                        "status": "UNAUTHENTICATED",
                    }
                },
            )
        return self.google.handle(method, url, headers, body)


def build_app(fake_windmill: FakeWindmill):
    """Starlette sub-app: Windmill API paths + ``/_sim/faults|calls|reset`` controls."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response as HttpResponse
    from starlette.routing import Route

    w = fake_windmill

    async def faults(req: Request):
        if req.method == "DELETE":
            w.clear_faults()
        else:
            try:
                w.set_faults(await req.json())
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "faults": dict(w._faults)})

    async def calls(_req: Request):
        return JSONResponse(w.calls)

    async def reset(_req: Request):
        w.reset()
        return JSONResponse({"ok": True})

    async def windmill(req: Request):
        url = req.url.path + (f"?{req.url.query}" if req.url.query else "")
        body = await req.body()
        # scripts run (and the timeout fault sleeps) synchronously: keep the loop free
        import anyio

        status, rbody, hdrs = await anyio.to_thread.run_sync(
            w.handle, req.method, url, dict(req.headers), body
        )
        return HttpResponse(rbody, status_code=status, headers=hdrs)

    app = Starlette(
        routes=[
            Route("/_sim/faults", faults, methods=["POST", "PUT", "DELETE"]),
            Route("/_sim/calls", calls, methods=["GET"]),
            Route("/_sim/reset", reset, methods=["POST"]),
            Route("/{path:path}", windmill, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        ]
    )
    app.state.fake_windmill = w
    return app
