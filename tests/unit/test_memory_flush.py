"""Unit tests for memory flush."""

import sys
from pathlib import Path
from unittest.mock import patch

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.memory_flush import flush_session_turn  # noqa: E402


def test_flush_session_turn_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("EVI_WORKSPACE", str(tmp_path))
    ok = flush_session_turn("s1", "hello", "world", [{"tool": "summarize_inbox"}])
    assert ok is True
    mem_dir = tmp_path / "memory"
    files = list(mem_dir.glob("*.md"))
    assert len(files) == 1
    assert "hello" in files[0].read_text(encoding="utf-8")
