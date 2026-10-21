"""evi-sim reporting: pass thresholds, aggregation, JSONL + Markdown output (SCN-SIM-07).

Pure functions over *records* (one dict per scenario attempt) so they are unit-testable
without the stack. Thresholds for ``--repeat N``: scenarios tagged ``critical`` or
``adversarial`` need N/N; every other scenario needs ceil(2N/3) passes (N=3 -> 2/3).
An attempt skipped by the LLM budget makes its scenario incomplete -> not ok.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

STRICT_TAGS = {"critical", "adversarial"}
SKIPPED = "skipped (budget)"


def required_passes(tags: list[str], n: int) -> int:
    if STRICT_TAGS & set(tags):
        return n
    return math.ceil(2 * n / 3)


def _prices() -> tuple[float, float, float]:
    def f(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, "").strip() or default)
        except ValueError:
            return default

    return f("EVI_SIM_PRICE_IN_USD", 0.30), f("EVI_SIM_PRICE_OUT_USD", 2.50), f("EVI_SIM_USD_BRL", 5.5)


def estimate_cost(tokens_in: int, tokens_out: int) -> tuple[float, float]:
    """(USD, BRL). tokens_out already includes reasoning/thinking (billed as output)."""
    p_in, p_out, fx = _prices()
    usd = (tokens_in * p_in + tokens_out * p_out) / 1_000_000
    return usd, usd * fx


def token_totals(records: list[dict]) -> dict:
    tin = sum(r.get("tokens_in", 0) for r in records)
    tout = sum(r.get("tokens_out", 0) for r in records)
    usd, brl = estimate_cost(tin, tout)
    return {
        "tokens_in": tin,
        "tokens_out": tout,
        "tokens_reasoning": sum(r.get("tokens_reasoning", 0) for r in records),
        "cost_usd": usd,
        "cost_brl": brl,
    }


def attempt_record(scenario_id: str, tags: list[str], attempt: int, res) -> dict:
    tin = int(getattr(res, "tokens_in", 0) or 0)
    tout = int(getattr(res, "tokens_out", 0) or 0)
    usd, brl = estimate_cost(tin, tout)
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
        "llm_served": int(getattr(res, "llm_served", 0) or 0),
        "tokens_in": tin,
        "tokens_out": tout,
        "tokens_reasoning": int(getattr(res, "tokens_reasoning", 0) or 0),
        "cost_usd": round(usd, 6),
        "cost_brl": round(brl, 6),
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
        "llm_served": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_reasoning": 0,
        "cost_usd": 0.0,
        "cost_brl": 0.0,
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


def calls_label(real: int, served: int) -> str:
    """SCN-SIM-11: calls that reached a real provider vs answered from a cassette."""
    return f"real {real} · served {served}"


def _served(records: list[dict]) -> int:
    return sum(r.get("llm_served", 0) for r in records)


def _llm_line(records: list[dict], meta: dict) -> str:
    t = token_totals(records)
    return (
        f"LLM: {calls_label(meta['llm_calls'], _served(records))}, {t['tokens_in']} in / {t['tokens_out']} out tok "
        f"({t['tokens_reasoning']} reasoning), ≈ R$ {t['cost_brl']:.2f} (US$ {t['cost_usd']:.4f})"
    )


def console_summary(summary: dict, meta: dict, records: list[dict] | None = None) -> str:
    lines = []
    for s in summary["scenarios"]:
        lines.append(f"{s['status']:<16} {s['scenario']}  {s['passed']}/{s['runs']} (need {s['required']}/{meta['repeat']})" + (f"  - {s['reason']}" if s["reason"] else ""))
    lines.append(f"LLM calls: {meta['llm_calls']} real (max {meta['max_llm_calls']})" + ("  BUDGET REACHED - partial report" if meta["budget_hit"] else ""))
    if records is not None:
        lines.append(_llm_line(records, meta))
    lines.append("RESULT: " + ("OK" if summary["ok"] else "FAILED"))
    return "\n".join(lines)


def to_markdown(records: list[dict], summary: dict, meta: dict) -> str:
    out = [
        f"# evi-sim report {meta['ts']}",
        "",
        f"- repeat: {meta['repeat']}",
        f"- LLM calls: {calls_label(meta['llm_calls'], _served(records))} (budget {meta['max_llm_calls']} real)" + (" - **budget reached, partial report**" if meta["budget_hit"] else ""),
        f"- tokens: {token_totals(records)['tokens_in']} in / {token_totals(records)['tokens_out']} out "
        f"({token_totals(records)['tokens_reasoning']} reasoning)",
        f"- estimated cost: R$ {token_totals(records)['cost_brl']:.2f} (US$ {token_totals(records)['cost_usd']:.4f})",
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
    out += ["", "## Attempts", "", "| Scenario | # | Status | LLM real/served | Tokens in/out | Cost (R$) | Duration (s) | Tools | Failure |", "|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        fail = (r["failures"][0] if r["failures"] else "").replace("|", "\\|").replace("\n", " ")
        out.append(f"| {r['scenario']} | {r['attempt']} | {r['status']} | {r['llm_calls']}/{r.get('llm_served', 0)} | {r.get('tokens_in', 0)}/{r.get('tokens_out', 0)} | {r.get('cost_brl', 0.0):.4f} | {r['duration_s']} | {', '.join(r['tools'])} | {fail} |")
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
