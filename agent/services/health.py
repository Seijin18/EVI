"""Dependency health checks for GET /health."""

from __future__ import annotations

import os
from typing import Any

_CHECK_TIMEOUT = 3.0


def _check_postgres() -> dict[str, Any]:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return {"ok": True, "detail": "skipped (no DATABASE_URL)"}
    try:
        import psycopg2

        conn = psycopg2.connect(url, connect_timeout=2)
        conn.close()
        return {"ok": True, "detail": "connected"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_qdrant() -> dict[str, Any]:
    url = os.getenv("QDRANT_URL", "").strip()
    if not url:
        return {"ok": True, "detail": "skipped (no QDRANT_URL)"}
    try:
        import httpx

        r = httpx.get(f"{url.rstrip('/')}/collections", timeout=_CHECK_TIMEOUT)
        if r.status_code < 500:
            return {"ok": True, "detail": f"http {r.status_code}"}
        return {"ok": False, "detail": f"http {r.status_code}"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_windmill() -> dict[str, Any]:
    hook = (
        os.getenv("WINDMILL_WEBHOOK_CALENDAR", "").strip()
        or os.getenv("WINDMILL_BASE_URL", "").strip()
    )
    if not hook:
        return {"ok": True, "detail": "skipped (no windmill url)"}
    try:
        import httpx

        # Windmill returns 401 without token — still proves reachability
        r = httpx.get(hook, timeout=_CHECK_TIMEOUT)
        if r.status_code < 500:
            return {"ok": True, "detail": f"http {r.status_code}"}
        return {"ok": False, "detail": f"http {r.status_code}"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_ollama() -> dict[str, Any]:
    base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
    try:
        import httpx

        r = httpx.get(f"{base}/api/tags", timeout=_CHECK_TIMEOUT)
        if r.status_code == 200:
            return {"ok": True, "detail": "tags ok"}
        return {"ok": False, "detail": f"http {r.status_code}"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_graph(graph_ready: bool) -> dict[str, Any]:
    if graph_ready:
        return {"ok": True, "detail": "initialized"}
    return {"ok": False, "detail": "not initialized"}


def run_health_checks(*, graph_ready: bool = True) -> dict[str, Any]:
    checks = {
        "graph": _check_graph(graph_ready),
        "postgres": _check_postgres(),
        "qdrant": _check_qdrant(),
        "windmill": _check_windmill(),
        "ollama": _check_ollama(),
    }
    evaluated = [c for c in checks.values() if not str(c.get("detail", "")).startswith("skipped")]
    if not evaluated:
        status = "ok"
    elif all(c["ok"] for c in evaluated):
        status = "ok"
    elif any(c["ok"] for c in evaluated):
        status = "degraded"
    else:
        status = "down"
    return {"status": status, "checks": checks}
