"""Sync the Google address book into WhatsApp contact names (SCN-NAME-01/03).

One Windmill call (`f/integrations/list_contacts`, OAuth `gcontacts`) returns only
`[{"name", "phones"}]`; `vcard_import.apply_entries` does the matching and writing.
Address-book contents never reach an LLM, and the report carries counts only.
"""

from __future__ import annotations

import json
import os
from typing import Any

from services.soft_fail import soft_fail

_RESOURCE_ENV = "WINDMILL_GCONTACTS_RESOURCE"
_COUNT_KEYS = ("parsed", "matched", "new_names", "changed", "unchanged",
               "ambiguous", "no_whatsapp", "protected_user")


def sync_enabled() -> bool:
    return os.getenv("EVI_CONTACT_NAMES_SYNC_ENABLED", "true").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _resource() -> str:
    value = os.getenv(_RESOURCE_ENV, "gcontacts").strip() or "gcontacts"
    if value.startswith("$var:"):
        value = value[5:]
    return value if value.startswith("$res:") else f"$res:{value}"


def _fetch_entries(timeout: int = 120) -> tuple[str, list[dict]]:
    """(status, entries): status is ok | oauth | error."""
    from integrations.factory import get_integration

    raw = get_integration().post(
        "list_contacts", {"gcontacts": _resource()}, timeout=timeout, wait_result=True
    )
    text = (raw or "").strip()
    try:
        data: Any = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, list):
        return "ok", [
            {"name": str(e.get("name") or ""), "phones": [str(p) for p in e.get("phones") or []]}
            for e in data
            if isinstance(e, dict)
        ]
    if isinstance(data, dict) and data.get("error"):
        return ("oauth" if data.get("reason") == "oauth" else "error"), []
    try:
        from services.response_format import format_windmill_oauth_error

        if format_windmill_oauth_error(text, "listar contatos", _RESOURCE_ENV):
            return "oauth", []
    except Exception as exc:  # noqa: BLE001
        soft_fail("contact_names.oauth_hint", exc)
    return "error", []


def sync(dry_run: bool = True) -> dict:
    """Fetch the address book and apply it. Counts only; never raises."""
    if not sync_enabled():
        return {"status": "disabled", "dry_run": dry_run}
    try:
        status, entries = _fetch_entries()
        if status != "ok":
            return {"status": status, "dry_run": dry_run}
        from services.vcard_import import apply_entries

        rep = apply_entries(entries, source="agenda", dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        soft_fail("contact_names.sync", exc)
        return {"status": "error", "dry_run": dry_run}
    return {"status": "ok", "dry_run": dry_run, **{k: rep.get(k, 0) for k in _COUNT_KEYS}}


def format_sync(report: dict) -> str:
    status = report.get("status")
    if status != "ok":
        return f"Sincronização de nomes: {status}"
    mode = "simulação (use --apply)" if report.get("dry_run") else "aplicado"
    return "Sincronização de nomes ({}): {}".format(
        mode, ", ".join(f"{k}={report.get(k, 0)}" for k in _COUNT_KEYS)
    )
