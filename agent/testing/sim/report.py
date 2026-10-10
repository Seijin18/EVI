"""evi-sim reporting: pass thresholds, aggregation, JSONL + Markdown output (SCN-SIM-07).

Pure functions over *records* (one dict per scenario attempt) so they are unit-testable
without the stack. Thresholds for ``--repeat N``: scenarios tagged ``critical`` or
``adversarial`` need N/N; every other scenario needs ceil(2N/3) passes (N=3 -> 2/3).
An attempt skipped by the LLM budget makes its scenario incomplete -> not ok.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

STRICT_TAGS = {"critical", "adversarial"}
SKIPPED = "skipped (budget)"


def required_passes(tags: list[str], n: int) -> int:
    if STRICT_TAGS & set(tags):
        return n
    return math.ceil(2 * n / 3)


def attempt_record(scenario_id: str, tags: list[str], attempt: int, res) -> dict:
    return {
        "scenario": scenario_id,
        "tags": list(tags),
        "attempt": attempt,
        "status": "pass" if res.passed else "fail",
        "passed": bool(res.passed),
        "failures": list(res.failures),
        "tools": list(res.tools_called),
        "latencies_s": [None if s.latency_s is None else round(s.latency_s, 2) for s in res.steps],
        "llm_calls": res.llm_calls,
        "duration_s": round(res.duration_s, 2),
    }


def skipped_record(scenario_id: str, tags: list[str], attempt: int) -> dict:
    return {
        "scenario": scenario_id,
        "tags": list(tags),
        "attempt": attempt,
        "status": SKIPPED,
        "passed": False,
        "failures": [],
        "tools": [],
        "latencies_s": [],
        "llm_calls": 0,
        "duration_s": 0.0,
    }


def summarize(records: list[dict], repeat: int) -> dict:
    by_scn: dict[str, list[dict]] = {}
    for r in records:
        by_scn.setdefault(r["scenario"], []).append(r)
    scenarios = []
    tag_stats: dict[str, dict] = {}
    for sid, recs in by_scn.items():
        tags = recs[0]["tags"]
        ran = [r for r in recs if r["status"] != SKIPPED]
        passed = sum(1 for r in ran if r["passed"])
        need = required_passes(tags, repeat)
        incomplete = len(ran) < repeat
        ok = not incomplete and passed >= need
        reason = ""
        if not ok:
            failing = next((r for r in ran if not r["passed"]), None)
            if failing:
                first = failing["failures"][0] if failing["failures"] else "failed"
                reason = f"attempt {failing['attempt']}: {first}"
            elif incomplete:
                reason = SKIPPED if not ran else f"incomplete: {len(ran)}/{repeat} attempts ran ({SKIPPED})"
        scenarios.append(
            {
                "scenario": sid,
                "tags": tags,
                "runs": len(ran),
                "passed": passed,
                "required": need,
                "rate": passed / len(ran) if ran else None,
                "ok": ok,
                "status": SKIPPED if not ran else ("PASS" if ok else "FAIL"),
                "reason": reason,
            }
        )
        for t in tags:
            st = tag_stats.setdefault(t, {"runs": 0, "passed": 0, "scenarios": 0, "failed_scenarios": 0})
            st["runs"] += len(ran)
            st["passed"] += passed
            st["scenarios"] += 1
            st["failed_scenarios"] += 0 if ok else 1
    for st in tag_stats.values():
        st["rate"] = st["passed"] / st["runs"] if st["runs"] else None
    return {
        "ok": bool(scenarios) and all(s["ok"] for s in scenarios),
        "scenarios": scenarios,
        "tags": dict(sorted(tag_stats.items())),
    }


def _pct(rate) -> str:
    return "n/a" if rate is None else f"{rate * 100:.0f}%"


def console_summary(summary: dict, meta: dict) -> str:
    lines = []
    for s in summary["scenarios"]:
        lines.append(f"{s['status']:<16} {s['scenario']}  {s['passed']}/{s['runs']} (need {s['required']}/{meta['repeat']})" + (f"  - {s['reason']}" if s["reason"] else ""))
    lines.append(f"LLM calls: {meta['llm_calls']} (max {meta['max_llm_calls']})" + ("  BUDGET REACHED - partial report" if meta["budget_hit"] else ""))
    lines.append("RESULT: " + ("OK" if summary["ok"] else "FAILED"))
    return "\n".join(lines)


def to_markdown(records: list[dict], summary: dict, meta: dict) -> str:
    out = [
        f"# evi-sim report {meta['ts']}",
        "",
        f"- repeat: {meta['repeat']}",
        f"- LLM calls: {meta['llm_calls']} (budget {meta['max_llm_calls']})" + (" - **budget reached, partial report**" if meta["budget_hit"] else ""),
        f"- result: **{'OK' if summary['ok'] else 'FAILED'}**",
        "",
        "## Scenarios",
        "",
        "| Scenario | Tags | Passed | Required | Rate | Status | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in summary["scenarios"]:
        reason = s["reason"].replace("|", "\\|").replace("\n", " ")
        out.append(f"| {s['scenario']} | {', '.join(s['tags'])} | {s['passed']}/{s['runs']} | {s['required']}/{meta['repeat']} | {_pct(s['rate'])} | {s['status']} | {reason} |")
    out += ["", "## Tags", "", "| Tag | Scenarios | Passed runs | Rate | Failed scenarios |", "|---|---|---|---|---|"]
    for t, st in summary["tags"].items():
        out.append(f"| {t} | {st['scenarios']} | {st['passed']}/{st['runs']} | {_pct(st['rate'])} | {st['failed_scenarios']} |")
    out += ["", "## Attempts", "", "| Scenario | # | Status | LLM calls | Duration (s) | Tools | Failure |", "|---|---|---|---|---|---|---|"]
    for r in records:
        fail = (r["failures"][0] if r["failures"] else "").replace("|", "\\|").replace("\n", " ")
        out.append(f"| {r['scenario']} | {r['attempt']} | {r['status']} | {r['llm_calls']} | {r['duration_s']} | {', '.join(r['tools'])} | {fail} |")
    return "\n".join(out) + "\n"


def write_reports(records: list[dict], summary: dict, meta: dict, out_dir: Path, ts: str) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl, md = out_dir / f"{ts}.jsonl", out_dir / f"{ts}.md"
    with jsonl.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({"ts": ts, **r}, ensure_ascii=False) + "\n")
    md.write_text(to_markdown(records, summary, meta), encoding="utf-8")
    return jsonl, md


def cmd_report(path: str | None, log_dir: Path) -> int:
    import sys

    if path:
        p = Path(path)
        if p.suffix == ".jsonl":
            p = p.with_suffix(".md")
    else:
        cands = sorted(Path(log_dir).glob("*.md"))
        if not cands:
            print(f"evi-sim: no reports in {log_dir}", file=sys.stderr)
            return 1
        p = cands[-1]
    if not p.is_file():
        print(f"evi-sim: report not found: {p}", file=sys.stderr)
        return 1
    print(p.read_text(encoding="utf-8"), end="")
    return 0
