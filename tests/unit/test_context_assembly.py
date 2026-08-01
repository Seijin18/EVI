"""Unit tests for context assembly."""

import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.context_assembly import build_context  # noqa: E402
from services.workspace import workspace_root  # noqa: E402


def test_build_context_includes_user_md():
    # USER.md is personal state and gitignored (openspec: "stop tracking
    # personal state"), so a fresh checkout never has it. Create a throwaway
    # one so this test is portable instead of depending on local dev state.
    root = workspace_root()
    user_md = root / "USER.md"
    created = not user_md.is_file()
    if created:
        user_md.write_text("# USER\n\nNome: Marcos\n", encoding="utf-8")
    try:
        assert user_md.is_file()
        ctx = build_context("telegram-1", "Revise meus emails")
        assert "Marcos" in ctx or "USER.md" in ctx
        assert "inbox-triage" in ctx.lower() or "RUNTIME SKILLS" in ctx
    finally:
        if created:
            user_md.unlink(missing_ok=True)


def test_build_context_commitment_skill():
    ctx = build_context("default", "listar compromissos pendentes")
    assert "commitment" in ctx.lower() or "compromisso" in ctx.lower()
