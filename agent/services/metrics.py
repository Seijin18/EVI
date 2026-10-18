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
TURNS_TOTAL = (
    Counter(
        "evi_turns_total",
        "Agent turns by channel and outcome",
        ["channel", "outcome"],
    )
    if _HAS_PROM
    else None
)
PROBE_FAILURES_TOTAL = (
    Counter(
        "evi_probe_failures_total",
        "Synthetic probe failures by check",
        ["check"],
    )
    if _HAS_PROM
    else None
)
BRIEFING_SENT_TOTAL = (
    Counter(
        "evi_briefing_sent_total",
        "Briefing delivery attempts by kind and outcome",
        ["kind", "ok"],
    )
    if _HAS_PROM
    else None
)
REMINDERS_FIRED_TOTAL = (
    Counter(
        "evi_reminders_fired_total",
        "Reminders delivered, by whether they were late (>5 min after due_at)",
        ["late"],
    )
    if _HAS_PROM
    else None
)
REMINDER_DRIFT_SECONDS = (
    Histogram(
        "evi_reminder_drift_seconds",
        "Seconds between a reminder's due_at and its delivery",
        buckets=(1, 5, 15, 30, 60, 120, 300, 900, 3600, 21600, 86400),
    )
    if _HAS_PROM
    else None
)
BRIEFING_REPLIED_TOTAL = (
    Counter(
        "evi_briefing_replied_total",
        "Briefings the user replied to within the engagement window",
        ["kind"],
    )
    if _HAS_PROM
    else None
)

_TURN_CHANNELS = frozenset({"telegram", "whatsapp_control", "api", "job"})
_TURN_OUTCOMES = frozenset({"ok", "error", "tool_failed"})
_PROBE_CHECKS = frozenset({"calendar", "tasks", "gmail", "telegram", "whatsapp"})
_BRIEFING_KINDS = frozenset({"morning", "evening"})


def _bounded(value: str, allowed: frozenset[str]) -> str:
    v = (value or "").strip().lower()
    return v if v in allowed else "other"


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


def record_turn(channel: str, outcome: str) -> None:
    if metrics_enabled() and TURNS_TOTAL is not None:
        TURNS_TOTAL.labels(
            channel=_bounded(channel, _TURN_CHANNELS),
            outcome=_bounded(outcome, _TURN_OUTCOMES),
        ).inc()


def record_probe_failure(check: str) -> None:
    if metrics_enabled() and PROBE_FAILURES_TOTAL is not None:
        PROBE_FAILURES_TOTAL.labels(check=_bounded(check, _PROBE_CHECKS)).inc()


def record_briefing_sent(kind: str, ok: bool) -> None:
    if metrics_enabled() and BRIEFING_SENT_TOTAL is not None:
        BRIEFING_SENT_TOTAL.labels(
            kind=_bounded(kind, _BRIEFING_KINDS), ok="true" if ok else "false"
        ).inc()


def record_reminder_fired(late: bool, drift_s: float) -> None:
    if not metrics_enabled():
        return
    if REMINDERS_FIRED_TOTAL is not None:
        REMINDERS_FIRED_TOTAL.labels(late="true" if late else "false").inc()
    if REMINDER_DRIFT_SECONDS is not None:
        REMINDER_DRIFT_SECONDS.observe(max(0.0, float(drift_s)))


def record_briefing_replied(kind: str) -> None:
    if metrics_enabled() and BRIEFING_REPLIED_TOTAL is not None:
        BRIEFING_REPLIED_TOTAL.labels(kind=_bounded(kind, _BRIEFING_KINDS)).inc()


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
        # Route template, never the raw URL (unbounded label cardinality, F14).
        route = request.scope.get("route")
        path = getattr(route, "path", None) or "unmatched"
        if REQUEST_COUNT is not None:
            REQUEST_COUNT.labels(
                method=request.method,
                path=path,
                status=str(response.status_code),
            ).inc()
        if REQUEST_LATENCY is not None:
            REQUEST_LATENCY.labels(method=request.method, path=path).observe(elapsed)
        return response
