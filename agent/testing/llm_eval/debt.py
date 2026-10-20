"""Debt-judge benchmark (debt_judge PROMPT_VERSION v1) against the real structured-LLM path.

    ./scripts/evi-test llm-eval debt [--provider openrouter|ollama|gemini]
        [--model M[,M2]] [--cases synthetic|real|all] [--repeat N]
        [--allow-cloud-real] [--min-accuracy 0.85]

Synthetic cases (fictitious) live in ``tests/eval/debt_cases.yaml``. Optional real cases
come from ``data/eval/debt_real.json`` (gitignored; same list format as the YAML plus
``context``/``message``/``expect``) and follow the same privacy rules as the promise eval.
The prompt is built by the SAME ``debt_judge.build_prompt`` production uses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import yaml

from testing.llm_eval.promise import _load_env, _percentile, _spent, _tz

REPO_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_PATH = REPO_ROOT / "tests" / "eval" / "debt_cases.yaml"
REAL_PATH = REPO_ROOT / "data" / "eval" / "debt_real.json"
MIN_ACCURACY = 0.85
SYNTHETIC_REF = (2026, 10, 12, 14, 0)


def _cases_from(items: list[dict], kind: str) -> list[dict]:
    return [
        {
            "id": c["id"], "kind": kind, "context": [(w, t) for w, t in c.get("context") or []],
            "message": c["message"], "expect": c.get("expect") or {},
            "ambiguous": bool(c.get("ambiguous")),
        }
        for c in items
    ]


def load_synthetic(path: Path = SYNTHETIC_PATH) -> list[dict]:
    return _cases_from(yaml.safe_load(path.read_text(encoding="utf-8")) or [], "synthetic")


def load_real(path: Path = REAL_PATH) -> list[dict]:
    if not path.is_file():
        return []
    return _cases_from(json.loads(path.read_text(encoding="utf-8")), "real")


def select_cases(
    which: str, provider: str, *, allow_cloud_real: bool = False,
    synthetic_path: Path = SYNTHETIC_PATH, real_path: Path = REAL_PATH,
) -> tuple[list[dict], list[str]]:
    cases: list[dict] = []
    notes: list[str] = []
    if which in ("synthetic", "all"):
        cases += load_synthetic(synthetic_path)
    if which in ("real", "all"):
        if provider == "gemini":
            notes.append("real cases skipped (gemini)")
        elif provider != "ollama" and not allow_cloud_real:
            notes.append(f"real cases skipped ({provider}: pass --allow-cloud-real to send them)")
        else:
            real = load_real(real_path)
            if not real:
                notes.append("real cases: none found (data/eval/debt_real.json)")
            cases += real
    return cases, notes


def build_prompt(case: dict) -> str:
    from services import debt_judge
    from services.untrusted import wrap_external

    ref = datetime(*SYNTHETIC_REF, tzinfo=_tz())
    n = len(case["context"])
    lines = []
    for i, (who, text) in enumerate(case["context"]):
        stamp = (ref - timedelta(minutes=5 * (n - i))).strftime("%H:%M")
        if who == "U":
            lines.append(f"[{stamp}] Usuário: {text}")
        else:  # same wrapping promise_context._line applies to contact text
            lines.append(
                f"[{stamp}] Contato: {wrap_external(text, source='whatsapp', max_chars=debt_judge.TEXT_MAX)}"
            )
    return debt_judge.build_prompt(lines, case["message"], ref.strftime("%H:%M"))


def score(case: dict, out: dict | None) -> dict:
    """Score one raw judge answer (None/invalid = LLM failed) against ``expect``."""
    valid = isinstance(out, dict) and isinstance(out.get("needs_reply"), bool)
    got = out["needs_reply"] if valid else None
    want = bool(case["expect"]["needs_reply"])
    return {
        "id": case["id"], "kind": case["kind"], "valid": valid, "got": got, "expect": want,
        "ambiguous": case.get("ambiguous", False), "ok": valid and got == want,
        # false-negative = judge says "no reply needed" on a real debt (the costly error)
        "fn": valid and want and not got, "fp": valid and not want and bool(got),
        "reason": str(out.get("reason") or "")[:120] if valid else "",
    }


def evaluate_case(case: dict, provider: str, models: list[str] | None) -> tuple[dict, float, float]:
    from services import llm_structured
    from services.debt_judge import DEBT_SCHEMA

    t0 = time.perf_counter()
    before = _spent()
    raw = llm_structured.run_structured(
        "DEBT", build_prompt(case), DEBT_SCHEMA, provider=provider, models=models
    )
    cost = max(0.0, _spent() - before)
    return score(case, raw if isinstance(raw, dict) else None), time.perf_counter() - t0, cost


def _pct(rows: list[dict], key: str) -> float:
    return sum(1 for r in rows if r[key]) / len(rows) if rows else 0.0


def run_model(cases: list[dict], provider: str, models: list[str] | None, repeat: int = 1) -> dict:
    rows: list[dict] = []
    lat: list[float] = []
    cost = 0.0
    for case in cases:
        if not case["expect"]:
            continue
        for _ in range(repeat):
            row, secs, c = evaluate_case(case, provider, models)
            rows.append(row)
            lat.append(secs)
            cost += c
    scored = [r for r in rows if not r["ambiguous"]]
    synth = [r for r in scored if r["kind"] == "synthetic"]
    return {
        "rows": rows, "n": len(scored), "excluded": len(rows) - len(scored),
        "accuracy": _pct(scored, "ok"), "valid": _pct(scored, "valid"),
        "fp": sum(r["fp"] for r in scored), "fn": sum(r["fn"] for r in scored),
        "p50": _percentile(lat, 0.5), "p95": _percentile(lat, 0.95), "cost": cost,
        "synthetic_accuracy": _pct(synth, "ok") if synth else None,
    }


def format_report(label: str, m: dict) -> list[str]:
    cost = f"US${m['cost']:.4f}" if m["cost"] else "n/a"
    lines = [
        f"{label}: n={m['n']} (excluded {m['excluded']}) accuracy={m['accuracy']:.0%} "
        f"json={m['valid']:.0%} FP={m['fp']} FN={m['fn']} "
        f"p50={m['p50']:.1f}s p95={m['p95']:.1f}s cost={cost}"
    ]
    for r in m["rows"]:
        mark = "ok  " if r["ok"] else "FAIL"
        amb = " (ambiguous, not scored)" if r["ambiguous"] else ""
        extra = f" reason={r['reason']!r}" if r["kind"] == "synthetic" and r["reason"] else ""
        lines.append(f"   {mark} {r['id']}: got={r['got']} expect={r['expect']}{amb}{extra}")
    return lines


def _default_run(provider: str) -> tuple[str, list[str] | None]:
    from services import llm_structured

    prov, mods = llm_structured._resolve("DEBT")
    if prov == provider and mods:
        return ",".join(mods), mods
    return "default", None


def run(
    which: str, provider: str, models: list[str], *, repeat: int = 1, allow_cloud_real: bool = False,
    min_accuracy: float = MIN_ACCURACY, out: Callable[[str], None] = print,
    synthetic_path: Path = SYNTHETIC_PATH, real_path: Path = REAL_PATH,
) -> int:
    cases, notes = select_cases(
        which, provider, allow_cloud_real=allow_cloud_real,
        synthetic_path=synthetic_path, real_path=real_path,
    )
    for n in notes:
        out(f"note: {n}")
    if not any(c["expect"] and not c["ambiguous"] for c in cases):
        out("no labelled cases to run")
        return 1
    runs = [(m, [m]) for m in models] if models else [_default_run(provider)]
    failed = False
    for label, mods in runs:
        m = run_model(cases, provider, mods, repeat)
        for line in format_report(f"{provider}:{label}", m):
            out(line)
        if m["accuracy"] < min_accuracy:
            out(f"GATE FAILED: accuracy {m['accuracy']:.0%} < {min_accuracy:.0%} ({provider}:{label})")
            failed = True
    return 1 if failed else 0


def main(argv: list[str], cwd: str | None = None) -> int:
    """``llm-eval debt ...`` (argv starts with the feature name)."""
    p = argparse.ArgumentParser(prog="evi-test llm-eval debt")
    p.add_argument("target", choices=["debt"])
    p.add_argument("--provider", default="openrouter", choices=["openrouter", "ollama", "gemini"])
    p.add_argument("--model", default="")
    p.add_argument("--cases", default="synthetic", choices=["synthetic", "real", "all"])
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--allow-cloud-real", action="store_true")
    p.add_argument("--min-accuracy", type=float, default=MIN_ACCURACY)
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 2)
    _load_env()
    models = [m.strip() for m in a.model.split(",") if m.strip()]
    return run(a.cases, a.provider, models, repeat=max(1, a.repeat),
               allow_cloud_real=a.allow_cloud_real, min_accuracy=a.min_accuracy)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
