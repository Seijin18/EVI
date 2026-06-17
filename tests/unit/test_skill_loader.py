"""Unit tests for runtime skill loader."""

import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.skill_loader import build_skills_block, match_skills  # noqa: E402


def test_match_inbox_skill():
    assert "inbox-triage" in match_skills("Revise meu gmail")


def test_match_commitment_skill():
    assert "commitment-review" in match_skills("listar compromissos")


def test_build_skills_block_non_empty():
    block = build_skills_block("apagar emails do aliexpress")
    assert "inbox-triage" in block
