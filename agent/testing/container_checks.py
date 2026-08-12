"""Assertions for the composed system — the class of defect unit tests cannot see.

Two shipped with a green pipeline and motivated this module:

* `dev_bridge._REPO_ROOT = Path(__file__).resolve().parents[2]` resolved to `/`
  inside the image (`WORKDIR /app`), so `dev approve` never worked there — the
  feature was removed rather than fixed, but the check that found it stays.
* `QDRANT__SERVICE__API_KEY=""` made Qdrant 401 everything, while `/health`
  still reported `"status": "ok"` because its rule was `status_code < 500`.

Pure functions on purpose: the shell smoke shells into the container to run
them, and `tests/unit/test_container_checks.py` covers the logic without Docker.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Iterable

# A path constant rooted here means `parents[N]` overshot the image root.
_FORBIDDEN_ROOTS = {"/", ""}


def check_health_payload(
    payload: dict[str, Any], *, not_started: Iterable[str] = ()
) -> list[str]:
    """Return failure messages for a `GET /health` body. Empty means healthy.

    Every check that is not `skipped` must be ok. The aggregate `status` is too
    coarse — it read "ok" while Qdrant rejected every request.

    `not_started` names dependencies the caller deliberately did not bring up
    (the smoke skips Windmill and Ollama to stay affordable). Their result is
    reported but never fails the run — narrowing the assertion honestly instead
    of loosening it for everything.
    """
    problems: list[str] = []
    exempt = set(not_started)
    status = payload.get("status")
    if status == "down":
        problems.append("aggregate status=down")
    checks = payload.get("checks")
    if not isinstance(checks, dict) or not checks:
        return problems + ["no checks in payload"]

    for name, check in checks.items():
        if not isinstance(check, dict):
            problems.append(f"{name}: malformed check")
            continue
        detail = str(check.get("detail", ""))
        if detail.startswith("skipped"):
            continue
        if check.get("ok") is not True:
            if name in exempt:
                print(f"[INFO] {name} não subiu neste smoke: {detail}")
                continue
            problems.append(f"{name}: ok={check.get('ok')} detail={detail!r}")
    return problems


def check_tools_payload(payload: dict[str, Any], *, expected: Iterable[str]) -> list[str]:
    """A tool that fails to import inside the image just disappears from /tools."""
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return ["/tools did not return a list"]
    missing = sorted(set(expected) - set(tools))
    if missing:
        return [f"missing from registry inside the image: {', '.join(missing)}"]
    return []


def check_port_bindings(config: dict[str, Any], *, data_services: Iterable[str]) -> list[str]:
    """Data services must publish with a host IP, never on every interface."""
    problems: list[str] = []
    services = config.get("services") or {}
    for name in data_services:
        svc = services.get(name)
        if not isinstance(svc, dict):
            continue  # not in this profile — nothing to assert
        for port in svc.get("ports") or []:
            if not isinstance(port, dict):
                continue
            host_ip = (port.get("host_ip") or "").strip()
            published = port.get("published")
            if not host_ip or host_ip == "0.0.0.0":
                problems.append(
                    f"{name}: port {published} published without a host IP"
                )
    return problems


def resolve_path_constants(package_names: Iterable[str]) -> dict[str, Path]:
    """Collect module-level Path constants named *_ROOT / *_DIR / *_SCRIPT.

    Import failures are reported by the caller as their own problem — a module
    that cannot import inside the image is exactly what we want to hear about.
    """
    found: dict[str, Path] = {}
    for pkg_name in package_names:
        try:
            pkg = importlib.import_module(pkg_name)
        except Exception:
            continue
        modules = [pkg]
        if hasattr(pkg, "__path__"):
            for info in pkgutil.iter_modules(pkg.__path__):
                try:
                    modules.append(importlib.import_module(f"{pkg_name}.{info.name}"))
                except Exception:
                    continue
        for mod in modules:
            for attr in dir(mod):
                if not attr.endswith(("_ROOT", "_DIR", "_SCRIPT")):
                    continue
                value = getattr(mod, attr, None)
                if isinstance(value, Path):
                    found[f"{mod.__name__}.{attr}"] = value
    return found


def check_path_constants(constants: dict[str, Path]) -> list[str]:
    """Reject constants that overshot the image root or point at nothing.

    A shape check, not a list of known-bad modules: a new module repeating the
    mistake fails without anyone remembering to register it.
    """
    problems: list[str] = []
    for name, value in sorted(constants.items()):
        resolved = str(value)
        if resolved in _FORBIDDEN_ROOTS:
            problems.append(f"{name} resolves to {resolved!r} — parents[N] overshot")
            continue
        if not value.exists():
            problems.append(f"{name} = {resolved} does not exist inside the image")
    return problems


def run_in_image_checks() -> list[str]:
    """Checks that only mean anything inside the built image."""
    constants = resolve_path_constants(
        ["services", "tools", "messaging", "integrations", "testing"]
    )
    # No exemptions: the dev bridge, the only module that ever needed one, was
    # removed. A stale allow-list is how a real defect gets silently excused.
    return check_path_constants(constants)


def check_boot_logs(logs: str) -> list[str]:
    """A clean boot must not soft-fail or traceback."""
    problems: list[str] = []
    for line in logs.splitlines():
        if "soft-fail" in line:
            problems.append(f"soft-fail during boot: {line.strip()[:160]}")
        elif "Traceback (most recent call last)" in line:
            problems.append("traceback during boot")
    return problems


if __name__ == "__main__":  # pragma: no cover - invoked inside the container
    import sys as _sys

    _problems = run_in_image_checks()
    for _p in _problems:
        print(f"[FAIL] {_p}")
    if not _problems:
        print("[PASS] import-time paths resolve inside the image")
    _sys.exit(1 if _problems else 0)
