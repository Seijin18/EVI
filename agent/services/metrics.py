"""Prometheus metrics (opt-in via EVI_METRICS_ENABLED)."""

from __future__ import annotations

import os
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    _HAS_PROM = True
except ImportError:
    _HAS_PROM = False
    CONTENT_TYPE_LATEST = "text/plain"

REQUEST_COUNT = (
    Counter(
        "evi_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    if _HAS_PROM
    else None
)
REQUEST_LATENCY = (
    Histogram(
        "evi_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "path"],
        buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 15.0, 60.0, 120.0),
    )
    if _HAS_PROM
    else None
)
WEBHOOK_LATENCY = (
    Histogram(
        "evi_webhook_duration_seconds",
        "Webhook handler latency",
        ["webhook"],
        buckets=(0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 15.0, 60.0),
    )
    if _HAS_PROM
    else None
)


def metrics_enabled() -> bool:
    if not _HAS_PROM:
        return False
    return os.getenv("EVI_METRICS_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )


def observe_webhook(webhook: str, duration_sec: float) -> None:
    if metrics_enabled() and WEBHOOK_LATENCY is not None:
        WEBHOOK_LATENCY.labels(webhook=webhook).observe(duration_sec)


def metrics_response() -> Response:
    if not metrics_enabled() or not _HAS_PROM:
        return Response(status_code=404, content="metrics disabled")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not metrics_enabled():
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = request.url.path
        if REQUEST_COUNT is not None:
            REQUEST_COUNT.labels(
                method=request.method,
                path=path,
                status=str(response.status_code),
            ).inc()
        if REQUEST_LATENCY is not None:
            REQUEST_LATENCY.labels(method=request.method, path=path).observe(elapsed)
        return response
