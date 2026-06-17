"""Unit tests for services/log_retention.py."""

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_agent = Path(__file__).resolve().parents[2] / "agent"
sys.path.insert(0, str(_agent))

from services.log_retention import append_jsonl, trim_jsonl  # noqa: E402


def _write_lines(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _ts(days_ago: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def test_trim_removes_old_entries():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.jsonl"
        _write_lines(path, [
            {"ts": _ts(10), "msg": "old"},
            {"ts": _ts(1), "msg": "recent"},
        ])
        removed = trim_jsonl(path, max_age_days=7)
        assert removed == 1
        lines = path.read_text().splitlines()
        assert len(lines) == 1
        assert "recent" in lines[0]


def test_trim_keeps_recent_entries():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.jsonl"
        _write_lines(path, [
            {"ts": _ts(1), "msg": "a"},
            {"ts": _ts(2), "msg": "b"},
        ])
        removed = trim_jsonl(path, max_age_days=7)
        assert removed == 0
        assert len(path.read_text().splitlines()) == 2


def test_trim_discards_malformed_lines():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.jsonl"
        path.write_text('{"ts": "' + _ts(1) + '", "msg": "ok"}\nnot-json\n')
        removed = trim_jsonl(path, max_age_days=7)
        assert removed == 1
        assert "ok" in path.read_text()


def test_append_creates_dir_and_appends():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sub" / "out.jsonl"
        append_jsonl(path, {"event": "test"})
        append_jsonl(path, {"event": "test2"})
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "test"


def test_trim_nonexistent_file():
    path = Path("/tmp/nonexistent_evi_test_abc123.jsonl")
    assert trim_jsonl(path) == 0


def test_trim_max_lines_keeps_newest():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.jsonl"
        _write_lines(path, [{"ts": _ts(i), "msg": f"line-{i}"} for i in range(5)])
        removed = trim_jsonl(path, max_age_days=30, max_lines=2)
        assert removed == 3
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["msg"] == "line-3"
        assert json.loads(lines[1])["msg"] == "line-4"


def test_prune_harness_logs():
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp)
        old = log_dir / "whatsapp_20260101_010101.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        old_ts = datetime.now(timezone.utc) - timedelta(days=3)
        import os as _os

        _os.utime(old, (old_ts.timestamp(), old_ts.timestamp()))
        harness = log_dir / "harness"
        harness.mkdir()
        recent = harness / "whatsapp_20260617_010101.jsonl"
        recent.write_text("{}\n", encoding="utf-8")
        from services.log_retention import prune_harness_logs  # noqa: E402

        removed = prune_harness_logs(log_dir, max_age_days=1)
        assert removed == 1
        assert not old.exists()
        assert recent.exists()


if __name__ == "__main__":
    test_trim_removes_old_entries()
    test_trim_keeps_recent_entries()
    test_trim_discards_malformed_lines()
    test_append_creates_dir_and_appends()
    test_trim_nonexistent_file()
    test_trim_max_lines_keeps_newest()
    test_prune_harness_logs()
    print("ok")
