"""Unit tests for context assembly."""

import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.context_assembly import build_context  # noqa: E402
from services.workspace import workspace_root  # noqa: E402


def test_build_context_includes_user_md():
    root = workspace_root()
    assert (root / "USER.md").is_file()
    ctx = build_context("telegram-1", "Revise meus emails")
    assert "Marcos" in ctx or "USER.md" in ctx
    assert "inbox-triage" in ctx.lower() or "RUNTIME SKILLS" in ctx


def test_build_context_commitment_skill():
    ctx = build_context("default", "listar compromissos pendentes")
    assert "commitment" in ctx.lower() or "compromisso" in ctx.lower()
