"""Cursor CLI dev bridge — propose / approve / execute with human-in-the-loop."""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "scripts" / "cursor-dev-runner.sh"


def dev_bridge_enabled() -> bool:
    return os.getenv("EVI_DEV_BRIDGE_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def _runs_dir() -> Path:
    raw = os.getenv("EVI_WORKSPACE", "").strip()
    base = Path(raw) if raw else _REPO_ROOT / "EVI_WORKSPACE"
    d = base / "dev-runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def propose_dev_task(description: str, *, requested_by: str = "") -> dict[str, Any]:
    if not dev_bridge_enabled():
        return {"ok": False, "error": "EVI_DEV_BRIDGE_ENABLED=false"}
    desc = (description or "").strip()
    if not desc:
        return {"ok": False, "error": "empty description"}
    job_id = uuid.uuid4().hex[:8]
    from db import create_dev_job

    create_dev_job(job_id, desc, requested_by=requested_by)
    return {
        "ok": True,
        "job_id": job_id,
        "status": "pending",
        "message": (
            f"Tarefa dev registrada `{job_id}`. "
            f"Aprove com: dev approve {job_id}"
        ),
    }


def approve_dev_task(job_id: str) -> dict[str, Any]:
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

    update_dev_job(jid, status="running")
    result = _run_cursor_plan(job.get("description") or "")
    status = "done" if result.get("exit_code") == 0 else "failed"
    log_path = result.get("log_path") or ""
    update_dev_job(
        jid,
        status=status,
        result_summary=(result.get("stdout") or "")[:2000],
        log_path=log_path,
    )
    return {"ok": status == "done", "job_id": jid, **result}


def status_dev_jobs(limit: int = 5) -> str:
    from db import list_dev_jobs

    rows = list_dev_jobs(limit=limit)
    if not rows:
        return "Nenhum job dev registrado."
    lines = ["Jobs dev:"]
    for r in rows:
        lines.append(
            f"- `{r['job_id']}` [{r['status']}] { (r.get('description') or '')[:60]}"
        )
    return "\n".join(lines)


def try_dev_command(text: str) -> str | None:
    """Parse dev approve / dev status / dev: ... from control chat."""
    if not dev_bridge_enabled():
        return None
    raw = (text or "").strip()
    lower = raw.lower()

    m = re.match(r"^dev\s+approve\s+([a-f0-9]{6,12})\b", lower)
    if m:
        out = approve_dev_task(m.group(1))
        if out.get("ok"):
            summary = (out.get("stdout") or "Concluído.")[:500]
            return f"Dev job `{m.group(1)}` executado.\n{summary}"
        return f"Falha dev job: {out.get('error') or out.get('stderr', '')[:200]}"

    if lower in ("dev status", "dev jobs"):
        return status_dev_jobs()

    if lower.startswith("dev:"):
        desc = raw[4:].strip()
        out = propose_dev_task(desc)
        return out.get("message") or out.get("error") or "Erro dev bridge."

    return None


def _run_cursor_plan(description: str) -> dict[str, Any]:
    if not _RUNNER.is_file():
        return {"exit_code": 1, "stderr": "cursor-dev-runner.sh missing", "stdout": ""}
    timeout = int(os.getenv("EVI_DEV_BRIDGE_TIMEOUT_SEC", "900"))
    log_path = _runs_dir() / f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.log"
    cmd = [str(_RUNNER), "plan", description]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "EVI_REPO_ROOT": str(_REPO_ROOT)},
        )
        log_path.write_text(
            proc.stdout + "\n--- stderr ---\n" + proc.stderr,
            encoding="utf-8",
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[:4000],
            "stderr": proc.stderr[:1000],
            "log_path": str(log_path),
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "stderr": "timeout", "stdout": "", "log_path": str(log_path)}
    except Exception as exc:
        return {"exit_code": 1, "stderr": str(exc)[:300], "stdout": ""}
