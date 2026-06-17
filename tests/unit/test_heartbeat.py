"""Unit tests for heartbeat stub."""

import sys
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.daily_summary import read_heartbeat_checklist, run_heartbeat_dry  # noqa: E402


def test_heartbeat_dry_returns_checklist():
    out = run_heartbeat_dry()
    assert "ok" in out
    assert "checklist" in out
    assert "compromissos" in read_heartbeat_checklist().lower()
