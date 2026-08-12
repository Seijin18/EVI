"""Structured tool outcome, replacing success-by-prose-inspection.

Tools used to decide whether an operation worked by reading their own output:
`if "failed" in result.lower()`, `'"status":"created"' in result`. That was not
only fragile, it was wrong in three places — most seriously
`commitment_tools._tool_succeeded`, which matched the substring "criad" and so
read a Windmill *error* mentioning "criada" as success, marking a commitment
scheduled with no event behind it.

The LangChain boundary is unchanged on purpose: tools stay `-> str` and return
`str(result)`, because `ToolNode` puts that text into `ToolMessage.content` and
it is what the model reads. The structure is for our code, not the model — same
split `SendResult` uses on the send path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# reason values
OAUTH = "oauth"
NOT_CONFIGURED = "not_configured"
HTTP_ERROR = "http_error"
UPSTREAM_ERROR = "upstream_error"
UNPARSEABLE = "unparseable"

# Success discriminators actually emitted by the Windmill scripts. They are not
# consistent: schedule_event and create_task say "created", the rest say "ok".
_SUCCESS_STATUS = frozenset({"ok", "created"})

# Sentinels our own client returns as plain strings. None contains "failed", so
# every `if "failed" in raw.lower()` missed them and they reached the model
# through a fallthrough branch as possibly-successful.
_NOT_CONFIGURED_PREFIXES = ("missing ", "unknown windmill operation")
_TRANSPORT_PREFIX = "windmill request failed"


@dataclass(frozen=True)
class ToolResult:
    """Outcome of one tool operation.

    Truthy on success and rendering to `message`, so existing call sites that do
    `if result:` or embed it in a string keep working untouched.
    """

    ok: bool
    message: str
    data: dict[str, Any] | None = None
    reason: str = ""
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        return self.message

    @classmethod
    def success(
        cls, message: str, *, data: dict[str, Any] | None = None
    ) -> "ToolResult":
        return cls(ok=True, message=message, data=data)

    @classmethod
    def failure(
        cls,
        message: str,
        *,
        reason: str = UPSTREAM_ERROR,
        detail: str = "",
        data: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            ok=False, message=message, data=data, reason=reason, detail=detail[:500]
        )


def parse_windmill_result(
    raw: str,
    *,
    action: str,
    resource_env: str = "",
    fallback_message: str = "",
) -> ToolResult:
    """Classify a Windmill response into a structured outcome. Never raises.

    `action` is the pt-BR verb used in error prose ("agendar 'X'", "listar
    tarefas"). `resource_env` enables the OAuth hint when the failure looks like
    an expired or missing Windmill resource.
    """
    from services.response_format import _parse_json_blob, format_windmill_oauth_error

    text = (raw or "").strip()
    lower = text.lower()

    if not text:
        return ToolResult.failure(
            f"Não foi possível {action}: resposta vazia do Windmill.",
            reason=UPSTREAM_ERROR,
        )

    # 1. Our own client's sentinels, before anything else — these are config
    #    errors, not upstream failures, and they used to slip through entirely.
    if lower.startswith(_NOT_CONFIGURED_PREFIXES):
        return ToolResult.failure(
            f"Não foi possível {action}: integração Windmill não configurada ({text[:120]}).",
            reason=NOT_CONFIGURED,
            detail=text,
        )

    # 2. OAuth/resource prose gets a remediation hint rather than a raw dump.
    if resource_env:
        hint = format_windmill_oauth_error(text, action, resource_env)
        if hint:
            return ToolResult.failure(hint, reason=OAUTH, detail=text)

    # 3. An empty 2xx body is reported by the client as the literal "ok".
    if text == "ok":
        return ToolResult.success(fallback_message or f"Operação '{action}' concluída.")

    # 4. Parse BEFORE any prose heuristic. Sniffing "failed" first would
    #    misread an envelope whose status *value* contains it (e.g. the cron
    #    scripts' `**body` splat writing status="failed_partially") — the very
    #    substring-matching this module exists to remove.
    blob = _parse_json_blob(text)

    if blob is None:
        if lower.startswith(_TRANSPORT_PREFIX) or "failed" in lower:
            return ToolResult.failure(
                f"Não foi possível {action}. {text[:400]}",
                reason=HTTP_ERROR,
                detail=text,
            )
        # Previously this fell through as neither success nor failure, and the
        # model saw an ambiguous string.
        return ToolResult.failure(
            f"Resposta inesperada ao {action}. {text[:400]}",
            reason=UNPARSEABLE,
            detail=text,
        )

    status = str(blob.get("status") or "").strip().lower()
    # `http_status` in the integration scripts, `http` in the cron trio.
    http_code = blob.get("http_status") or blob.get("http") or ""

    if status in _SUCCESS_STATUS:
        return ToolResult.success(fallback_message or "", data=blob)

    detail = str(blob.get("detail") or "")[:500]
    if status == "error":
        if resource_env:
            hint = format_windmill_oauth_error(detail or text, action, resource_env)
            if hint:
                return ToolResult.failure(hint, reason=OAUTH, detail=detail, data=blob)
        code = f" (HTTP {http_code})" if http_code else ""
        return ToolResult.failure(
            f"Erro ao {action}{code}: {detail or text[:300]}",
            reason=UPSTREAM_ERROR,
            detail=detail,
            data=blob,
        )

    # Valid JSON with an unrecognised status — the cron scripts can overwrite
    # `status` via their `**body` splat, so this is reachable.
    return ToolResult.failure(
        f"Resposta inesperada ao {action} (status={status or '?'}). {text[:300]}",
        reason=UNPARSEABLE,
        detail=text,
        data=blob,
    )
