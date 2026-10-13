"""Daily read-only probe of the integrations the assistant depends on.

Calls the production integration path (WindmillClient + Telegram getMe) directly,
without the LLM and without any write operation, so an expired OAuth shows up as
a warning at 06:30 instead of as a failed request at 15:00.

Read-only is enforced structurally: this module imports no LangChain tool and no
write helper (see tests/unit/test_probe.py, which inspects the imports).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import db
from integrations.factory import get_integration
from services import metrics
from services.soft_fail import soft_fail
from services.tool_result import OAUTH, ToolResult, parse_windmill_result

logger = logging.getLogger("evi.probe")

_FALLBACK_TZ = "America/Sao_Paulo"

# check name -> (label shown to the user, Windmill resource name in the reconnect hint)
_LABELS = {
    "calendar": "Google Calendar",
    "tasks": "Google Tasks",
    "gmail": "Gmail",
    "telegram": "Telegram",
}
_RESOURCE_DEFAULTS = {
    "calendar": ("WINDMILL_GCAL_RESOURCE", "gcal"),
    "tasks": ("WINDMILL_GTASKS_RESOURCE", "gtasks"),
    "gmail": ("WINDMILL_GMAIL_RESOURCE", "gmail"),
}


def _today() -> date:
    tz = os.getenv("EVI_TIMEZONE", "").strip() or _FALLBACK_TZ
    try:
        return datetime.now(ZoneInfo(tz)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(ZoneInfo(_FALLBACK_TZ)).date()


def _resource(check: str) -> str:
    env, default = _RESOURCE_DEFAULTS[check]
    value = os.getenv(env, default).strip() or default
    if value.startswith("$var:"):
        value = value[5:]
    if not value.startswith("$res:"):
        value = f"$res:{value}"
    return value


def _resource_name(check: str) -> str:
    return _resource(check).removeprefix("$res:")


def _windmill_check(
    operation: str, payload: dict[str, Any], *, action: str, resource_env: str, timeout: int
) -> ToolResult:
    raw = get_integration().post(operation, payload, timeout=timeout, wait_result=True)
    return parse_windmill_result(raw, action=action, resource_env=resource_env)


def _check_calendar(day: date) -> ToolResult:
    tz = os.getenv("EVI_TIMEZONE", "").strip() or _FALLBACK_TZ
    payload = {
        "gcal": _resource("calendar"),
        "calendar_id": os.getenv("WINDMILL_CALENDAR_ID", "primary").strip() or "primary",
        "timezone": tz,
        "days_ahead": 1,
        "max_results": 5,
        "on_date": day.isoformat(),
    }
    return _windmill_check(
        "list_events", payload, action="listar eventos",
        resource_env="WINDMILL_GCAL_RESOURCE", timeout=120,
    )


def _check_tasks(day: date) -> ToolResult:
    payload = {"gtasks": _resource("tasks"), "max_results": 1, "show_completed": False}
    return _windmill_check(
        "list_tasks", payload, action="listar tarefas",
        resource_env="WINDMILL_GTASKS_RESOURCE", timeout=120,
    )


def _check_gmail(day: date) -> ToolResult:
    payload = {"max_messages": 1, "gmail": _resource("gmail")}
    return _windmill_check(
        "summarize_inbox", payload, action="acessar o Gmail",
        resource_env="WINDMILL_GMAIL_RESOURCE", timeout=180,
    )


def _check_telegram(day: date) -> ToolResult:
    from services.telegram_poller import _api_get

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return ToolResult.failure("TELEGRAM_BOT_TOKEN ausente", reason="not_configured")
    try:
        _api_get(token, "getMe")
    except Exception as exc:  # urllib/HTTP/RuntimeError: all mean "bot unreachable"
        return ToolResult.failure("getMe falhou", reason="http_error", detail=str(exc))
    return ToolResult.success("ok")


_CHECKS: list[tuple[str, Callable[[date], ToolResult]]] = [
    ("calendar", _check_calendar),
    ("tasks", _check_tasks),
    ("gmail", _check_gmail),
    ("telegram", _check_telegram),
]


def _warning_text(check: str, reason: str, detail: str) -> str:
    label = _LABELS[check]
    if reason == OAUTH:
        name = _resource_name(check)
        return (
            f"⚠️ O acesso ao {label} expirou. "
            f"Reconecte em Windmill → Resources → {name} (reconectar OAuth)."
        )
    if reason == "not_configured":
        return f"⚠️ {label} não está configurado. Configure a integração no .env e no Windmill."
    # O motivo de máquina (http_error, upstream_error…) fica no log/DB; o usuário lê causa + o que fazer.
    return (
        f"⚠️ {label} não respondeu à verificação diária de hoje. "
        "Costuma ser instabilidade passageira — o EVI tenta de novo amanhã; "
        "se o aviso se repetir, rode make status."
    )


def _notify(day: date, check: str, reason: str, detail: str) -> bool:
    """One warning per integration per day. Telegram itself can't warn via Telegram."""
    if check == "telegram":
        return False
    claimed = False
    try:
        # Claim before sending so overlapping runs cannot double-send.
        if not db.claim_probe_notification(day, check):
            return False
        claimed = True
        from services.telegram_notify import send_telegram_message

        if not send_telegram_message(_warning_text(check, reason, detail)):
            db.release_probe_notification(day, check)  # next run may try again
            return False
        db.mark_probe_notified(day, check)
        return True
    except Exception as exc:
        soft_fail("probe.notify", exc)
        if claimed:
            try:
                db.release_probe_notification(day, check)
            except Exception as rel_exc:
                soft_fail("probe.notify_release", rel_exc)
        return False


def notify_oauth(check: str) -> bool:
    """In-turn OAuth warning; shares the probe's per-day claim so only one goes out."""
    if check not in _RESOURCE_DEFAULTS:
        return False
    return _notify(_today(), check, OAUTH, "")


def _run_check(fn, day: date) -> ToolResult:
    try:
        return fn(day)
    except Exception as exc:
        return ToolResult.failure("exceção", reason="upstream_error", detail=str(exc))


def run_probe() -> dict:
    """Run the four read-only checks. Each is timed and soft-failed independently."""
    day = _today()
    results: dict[str, dict[str, Any]] = {}
    for check, fn in _CHECKS:
        started = time.perf_counter()
        out = _run_check(fn, day)
        if not out.ok and check != "telegram":
            # One retry: an OAuth access token can expire seconds before Windmill
            # refreshes it (seen at 06:30 with a 401 that was gone a minute later).
            time.sleep(float(os.getenv("EVI_PROBE_RETRY_SEC", "20")))
            out = _run_check(fn, day)
        ms = int((time.perf_counter() - started) * 1000)
        reason = None if out.ok else (out.reason or "upstream_error")
        entry: dict[str, Any] = {"ok": bool(out.ok), "reason": reason, "ms": ms, "notified": False}
        try:
            db.insert_probe(day, check, bool(out.ok), reason, ms)
        except Exception as exc:
            soft_fail("probe.insert", exc)
        if not out.ok:
            logger.warning("probe %s failed: %s %s", check, reason, out.detail[:200])
            try:
                metrics.record_probe_failure(check)
            except Exception as exc:
                soft_fail("probe.metric", exc)
            entry["notified"] = _notify(day, check, reason or "", out.detail)
        results[check] = entry
    return {"ok": all(r["ok"] for r in results.values()), "day": day.isoformat(), "checks": results}
