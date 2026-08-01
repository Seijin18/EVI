"""Dev bridge — propose / approve / execute via a pluggable CLI backend (human-in-the-loop)."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]

_APPROVE_RE = re.compile(
    r"^dev\s+approve\s+([a-f0-9]{6,12})(?:\s+--cli=(\w+))?\b"
)
_PROPOSE_CLI_RE = re.compile(r"\s+--cli=(\w+)\s*$")


def dev_bridge_enabled() -> bool:
    return os.getenv("EVI_DEV_BRIDGE_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def _timeout_sec() -> int:
    return int(os.getenv("EVI_DEV_BRIDGE_TIMEOUT_SEC", "900"))


def propose_dev_task(
    description: str, *, requested_by: str = "", backend: str = ""
) -> dict[str, Any]:
    if not dev_bridge_enabled():
        return {"ok": False, "error": "EVI_DEV_BRIDGE_ENABLED=false"}
    desc = (description or "").strip()
    if not desc:
        return {"ok": False, "error": "empty description"}

    resolved_backend = (backend or os.getenv("EVI_DEV_CLI", "claude")).strip().lower()

    job_id = uuid.uuid4().hex[:8]
    from db import create_dev_job

    create_dev_job(job_id, desc, requested_by=requested_by, backend=resolved_backend)

    message = (
        f"Tarefa dev registrada `{job_id}` ({resolved_backend}). "
        f"Aprove com: dev approve {job_id}"
    )

    if _propose_mode() == "plan":
        from devcli.factory import resolve_dev_cli

        try:
            cli = resolve_dev_cli(resolved_backend)
        except ValueError as exc:
            return {
                "ok": True,
                "job_id": job_id,
                "status": "pending",
                "message": message + f"\n(preview indisponível: {exc})",
            }

        result = cli.run(
            "plan", desc, repo_root=_REPO_ROOT, timeout_sec=_timeout_sec()
        )
        preview = (result.stdout or result.stderr or "").strip()[:1500]
        if preview:
            message += f"\n\nPreview (plan):\n{preview}"

    return {"ok": True, "job_id": job_id, "status": "pending", "message": message}


def approve_dev_task(
    job_id: str, *, backend_override: str | None = None
) -> dict[str, Any]:
    if not dev_bridge_enabled():
        return {"ok": False, "error": "EVI_DEV_BRIDGE_ENABLED=false"}
    jid = (job_id or "").strip().lower()
    if not jid:
        return {"ok": False, "error": "missing job_id"}
    from db import get_dev_job, update_dev_job

    job = get_dev_job(jid)
    if not job:
        return {"ok": False, "error": f"job {jid} not found"}
    if job.get("status") not in ("pending", "failed"):
        return {"ok": False, "error": f"job status={job.get('status')}"}

    from devcli.factory import get_dev_cli, resolve_dev_cli

    backend_name = backend_override or job.get("backend") or ""
    try:
        cli = resolve_dev_cli(backend_name) if backend_name else get_dev_cli()
    except ValueError as exc:
        return {"ok": False, "job_id": jid, "error": str(exc)}

    update_dev_job(jid, status="running")
    result = cli.run(
        "apply",
        job.get("description") or "",
        repo_root=_REPO_ROOT,
        timeout_sec=_timeout_sec(),
    )
    status = "done" if result.exit_code == 0 else "failed"
    update_dev_job(
        jid,
        status=status,
        result_summary=(result.stdout or "")[:2000],
        log_path=result.log_path,
        mode="apply",
        branch=result.branch,
    )
    return {
        "ok": status == "done",
        "job_id": jid,
        "backend": cli.name,
        "mode": "apply",
        "branch": result.branch,
        "diff_stat": result.diff_stat,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "log_path": result.log_path,
    }


def status_dev_jobs(limit: int = 5) -> str:
    from db import list_dev_jobs

    rows = list_dev_jobs(limit=limit)
    if not rows:
        return "Nenhum job dev registrado."
    lines = ["Jobs dev:"]
    for r in rows:
        tag = "/".join(x for x in (r.get("backend"), r.get("mode")) if x)
        branch = f" branch={r['branch']}" if r.get("branch") else ""
        lines.append(
            f"- `{r['job_id']}` [{r['status']}]"
            f"{f' ({tag})' if tag else ''}{branch} "
            f"{(r.get('description') or '')[:60]}"
        )
    return "\n".join(lines)


def _propose_mode() -> str:
    from db import get_dev_bridge_setting

    return get_dev_bridge_setting("propose_mode", "default")


def _set_propose_mode(mode: str) -> str:
    from db import set_dev_bridge_setting

    set_dev_bridge_setting("propose_mode", mode)
    return mode


def try_dev_command(text: str) -> str | None:
    """Parse dev approve / dev status / dev mode / dev: ... from control chat."""
    if not dev_bridge_enabled():
        return None
    raw = (text or "").strip()
    lower = raw.lower()

    m = _APPROVE_RE.match(lower)
    if m:
        job_id, cli_override = m.group(1), m.group(2)
        out = approve_dev_task(job_id, backend_override=cli_override)
        if out.get("ok"):
            summary = (out.get("stdout") or "Concluído.")[:500]
            branch = out.get("branch")
            branch_note = f"\nBranch: `{branch}`" if branch else ""
            return (
                f"Dev job `{job_id}` executado ({out.get('backend')})."
                f"{branch_note}\n{summary}"
            )
        return f"Falha dev job: {out.get('error') or (out.get('stderr') or '')[:200]}"

    if lower in ("dev status", "dev jobs"):
        return status_dev_jobs()

    if lower == "dev mode":
        return f"Modo de propose atual: {_propose_mode()}"

    if lower == "dev mode plan":
        _set_propose_mode("plan")
        return "Modo de propose: plan (preview síncrono ao propor)."

    if lower == "dev mode default":
        _set_propose_mode("default")
        return "Modo de propose: default (registra sem rodar preview)."

    if lower.startswith("dev:"):
        desc = raw[4:].strip()
        cli_override = None
        cli_m = _PROPOSE_CLI_RE.search(desc)
        if cli_m:
            cli_override = cli_m.group(1)
            desc = desc[: cli_m.start()].strip()
        out = propose_dev_task(desc, backend=cli_override or "")
        return out.get("message") or out.get("error") or "Erro dev bridge."

    return None
