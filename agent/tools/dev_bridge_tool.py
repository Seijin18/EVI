"""LangGraph tools for the dev bridge (approval required)."""

from __future__ import annotations

from langchain_core.tools import tool

from services.dev_bridge import (
    dev_bridge_enabled,
    propose_dev_task,
    status_dev_jobs,
)


@tool
def propose_dev_task_tool(description: str, cli: str = "") -> str:
    """
    Register a development task for CLI execution (requires user approval).
    Use when the user asks to fix tests, refactor code, or run OpenSpec apply.
    Optional `cli` picks the backend (e.g. "claude"); defaults to EVI_DEV_CLI.
    User must reply 'dev approve <job_id>' on control chat before execution.
    """
    if not dev_bridge_enabled():
        return "Dev bridge desabilitado (EVI_DEV_BRIDGE_ENABLED=false)."
    out = propose_dev_task(description, backend=cli)
    return out.get("message") or out.get("error") or "Erro."


@tool
def status_dev_jobs_tool() -> str:
    """List recent dev bridge jobs and their status."""
    if not dev_bridge_enabled():
        return "Dev bridge desabilitado."
    return status_dev_jobs()
