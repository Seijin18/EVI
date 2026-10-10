"""evi-sim reporting: thresholds, aggregation, budget, JSONL/Markdown (SCN-SIM-07)."""

import json
from types import SimpleNamespace

from testing.sim import report, schema


def _recs(sid, tags, outcomes, reason="calendar.count: expected 1 got 0"):
    return [
        {
            "scenario": sid, "tags": tags, "attempt": i + 1, "status": "pass" if ok else "fail",
            "passed": ok, "failures": [] if ok else [f"step 0 (telegram): {reason}"],
            "tools": ["schedule_event"], "latencies_s": [1.5], "llm_calls": 3, "duration_s": 4.0,
        }
        for i, ok in enumerate(outcomes)
    ]


def test_required_passes():
    assert report.required_passes(["critical"], 3) == 3
    assert report.required_passes(["adversarial", "x"], 5) == 5
    assert report.required_passes(["calendar"], 3) == 2
    assert report.required_passes([], 1) == 1
    assert report.required_passes([], 5) == 4


def test_critical_two_of_three_fails_with_failing_attempt_reason():
    s = report.summarize(_recs("A", ["critical"], [True, False, True]), 3)
    assert not s["ok"]
    row = s["scenarios"][0]
    assert (row["passed"], row["required"], row["status"]) == (2, 3, "FAIL")
    assert "attempt 2" in row["reason"] and "calendar.count" in row["reason"]


def test_normal_two_of_three_passes():
    s = report.summarize(_recs("A", ["calendar"], [True, False, True]), 3)
    assert s["ok"] and s["scenarios"][0]["status"] == "PASS"


def test_adversarial_needs_all():
    assert report.summarize(_recs("A", ["adversarial"], [True, True, True]), 3)["ok"]
    assert not report.summarize(_recs("A", ["adversarial"], [True, True, False]), 3)["ok"]


def test_per_tag_aggregation_and_overall_exit():
    recs = _recs("A", ["calendar", "smoke"], [True, True, False]) + _recs("B", ["calendar"], [True, True, True])
    s = report.summarize(recs, 3)
    assert s["ok"]
    assert (s["tags"]["calendar"]["passed"], s["tags"]["calendar"]["runs"]) == (5, 6)
    assert s["tags"]["smoke"]["rate"] == 2 / 3
    assert s["tags"]["calendar"]["scenarios"] == 2


def test_budget_skip_marks_incomplete_and_fails(tmp_path):
    recs = _recs("A", [], [True]) + [report.skipped_record("A", [], 2), report.skipped_record("A", [], 3)]
    recs += [report.skipped_record("B", ["critical"], n) for n in (1, 2, 3)]
    s = report.summarize(recs, 3)
    assert not s["ok"]
    by = {r["scenario"]: r for r in s["scenarios"]}
    assert by["B"]["status"] == report.SKIPPED and by["A"]["runs"] == 1
    meta = {"ts": "T", "repeat": 3, "max_llm_calls": 1, "llm_calls": 3, "budget_hit": True}
    jsonl, md = report.write_reports(recs, s, meta, tmp_path, "T")
    assert jsonl.exists() and md.exists()
    assert "partial report" in md.read_text()
    assert any(json.loads(l)["status"] == report.SKIPPED for l in jsonl.read_text().splitlines())


def test_jsonl_record_fields_and_markdown_table(tmp_path):
    res = SimpleNamespace(
        passed=False, failures=["step 0 (telegram): reply_within_s: no reply"], tools_called=["list_events"],
        steps=[SimpleNamespace(latency_s=2.345), SimpleNamespace(latency_s=None)], llm_calls=4, duration_s=9.876,
    )
    rec = report.attempt_record("SIM-X", ["critical"], 2, res)
    for k in ("scenario", "tags", "attempt", "status", "failures", "tools", "latencies_s", "llm_calls", "duration_s"):
        assert k in rec
    assert rec["latencies_s"] == [2.35, None] and rec["llm_calls"] == 4
    s = report.summarize([rec], 1)
    meta = {"ts": "T", "repeat": 1, "max_llm_calls": 200, "llm_calls": 4, "budget_hit": False}
    jsonl, md = report.write_reports([rec], s, meta, tmp_path, "T")
    row = json.loads(jsonl.read_text().splitlines()[0])
    assert row["scenario"] == "SIM-X" and row["failures"] and row["tools"] == ["list_events"]
    text = md.read_text()
    assert "| Scenario | Tags |" in text and "| SIM-X |" in text and "| Tag |" in text
    assert "FAILED" in text


def test_cmd_report_prints_latest(tmp_path, capsys):
    (tmp_path / "20260101-000000.md").write_text("old\n")
    (tmp_path / "20260102-000000.md").write_text("new\n")
    assert report.cmd_report(None, tmp_path) == 0
    assert capsys.readouterr().out == "new\n"
    assert report.cmd_report(str(tmp_path / "missing.md"), tmp_path) == 1


def test_no_reply_expectation():
    exp = {"no_reply": True}
    assert schema.eval_expect(exp, {"reply": None}) == []
    assert any("no_reply" in f for f in schema.eval_expect(exp, {"reply": "oi"}))


def test_no_reply_validation():
    base = {"id": "X", "steps": [{"telegram": "oi", "expect": {"no_reply": True, "no_reply_window_s": 5}}]}
    assert schema.parse_scenario(base).steps[0].expect["no_reply"] is True
    bad = {"id": "X", "steps": [{"job": "heartbeat", "expect": {"no_reply": True}}]}
    try:
        schema.parse_scenario(bad)
    except schema.ScenarioError:
        pass
    else:
        raise AssertionError("expected ScenarioError")
