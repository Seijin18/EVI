"""Outbound send result + shared retry.

A reply that cannot be delivered used to collapse into a bare `return False`,
so a transient network blip silently discarded an answer the agent had already
computed, with nothing in the log saying why. This keeps sends non-raising —
a failed delivery must not turn a successful turn into a 500 — while making the
failure attributable.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

# reason values
TRANSPORT = "transport"
HTTP_4XX = "http_4xx"
HTTP_5XX = "http_5xx"
NOT_CONFIGURED = "not_configured"
EMPTY_TEXT = "empty_text"

_DEFAULT_ATTEMPTS = 2
_DEFAULT_BACKOFF = 1.5


@dataclass(frozen=True)
class SendResult:
    """Outcome of one outbound message.

    Truthy when delivered, so existing `if send_...(...)` call sites and the
    `telegram_sent` / `whatsapp_sent` booleans keep working unchanged.
    """

    sent: bool
    reason: str = ""
    attempts: int = 0
    detail: str = ""

    def __bool__(self) -> bool:
        return self.sent

    @classmethod
    def ok(cls, attempts: int = 1) -> "SendResult":
        return cls(sent=True, attempts=attempts)

    @classmethod
    def fail(cls, reason: str, *, attempts: int = 0, detail: str = "") -> "SendResult":
        return cls(sent=False, reason=reason, attempts=attempts, detail=detail[:200])


def send_outcome(result: object) -> tuple[bool, str]:
    """Normalize a send outcome into `(sent, reason)` for a JSON response.

    Accepts a plain bool too, so call sites like `x if cond else False` keep
    working without a branch. Keeps `telegram_sent`/`whatsapp_sent` a real bool
    on the wire rather than leaking the dataclass into the response body.
    """
    if isinstance(result, SendResult):
        return result.sent, ("" if result.sent else result.reason)
    return bool(result), ""


def _attempts() -> int:
    try:
        value = int(os.getenv("EVI_SEND_RETRY_ATTEMPTS", str(_DEFAULT_ATTEMPTS)))
    except ValueError:
        return _DEFAULT_ATTEMPTS
    return max(1, value)


def _backoff() -> float:
    try:
        value = float(os.getenv("EVI_SEND_RETRY_BACKOFF_SEC", str(_DEFAULT_BACKOFF)))
    except ValueError:
        return _DEFAULT_BACKOFF
    return max(0.0, value)


def post_with_retry(
    request: urllib.request.Request,
    *,
    timeout: int,
    context: str,
) -> SendResult:
    """POST with a bounded retry. Never raises.

    Retries transport errors and 5xx. A 4xx is returned immediately — a bad
    token, chat id or closed instance fails identically on the next attempt, so
    retrying only delays the (now visible) error.
    """
    attempts = _attempts()
    backoff = _backoff()
    last_reason = TRANSPORT
    last_detail = ""

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                if 200 <= resp.status < 300:
                    return SendResult.ok(attempts=attempt)
                last_reason = HTTP_5XX if resp.status >= 500 else HTTP_4XX
                last_detail = f"http {resp.status}"
                if last_reason == HTTP_4XX:
                    break
        except urllib.error.HTTPError as exc:
            last_detail = f"http {exc.code}"
            if exc.code < 500:
                failed = SendResult.fail(HTTP_4XX, attempts=attempt, detail=last_detail)
                _report(context, failed)
                return failed
            last_reason = HTTP_5XX
        except (urllib.error.URLError, OSError) as exc:
            last_reason = TRANSPORT
            last_detail = f"{type(exc).__name__}: {exc}"

        if attempt < attempts:
            time.sleep(backoff)

    result = SendResult.fail(last_reason, attempts=attempts, detail=last_detail)
    _report(context, result)
    return result


def _report(context: str, result: SendResult) -> None:
    """One log line per dropped message — not one per attempt."""
    from services.soft_fail import soft_fail

    soft_fail(
        context,
        RuntimeError(result.detail or result.reason),
        detail=f"reason={result.reason} attempts={result.attempts}",
    )
