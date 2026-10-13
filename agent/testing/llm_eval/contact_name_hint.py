"""Contact-name-hint benchmark (task ``CONTACT_NAME_HINT``) against the real structured-LLM path.

    ./scripts/evi-test llm-eval contact-name-hint [--provider openrouter|ollama|gemini]
        [--model M[,M2]] [--cases synthetic|real|all] [--repeat N]
        [--allow-cloud-real] [--min-accuracy 0.85]

Synthetic cases (fictitious) live in ``tests/eval/contact_name_hint_cases.yaml``. Real cases
come only from ``data/eval/contact_name_hint_real.json`` (gitignored, mode 0600) and follow
the same privacy matrix as the other evaluators: never sent to Gemini, sent to OpenRouter only
with ``--allow-cloud-real`` (ZDR is enforced inside ``run_structured``), always to ollama. Real
cases have no labels: a hint is only checked for surviving the production validation, and their
content is never printed. Prompt and validation are the production ones (``contact_names``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable

import yaml

from testing.llm_eval.promise import REPO_ROOT, _load_env, _percentile, _spent, norm

SYNTHETIC_PATH = REPO_ROOT / "tests" / "eval" / "contact_name_hint_cases.yaml"
REAL_PATH = REPO_ROOT / "data" / "eval" / "contact_name_hint_real.json"
MIN_ACCURACY = 0.85


def _case(cid, kind, contact, messages, expect) -> dict:
    """messages: list of (YYYY-MM-DD, from_me, text)."""
    return {"id": cid, "kind": kind, "contact": contact, "messages": messages, "expect": expect or {}}


def load_synthetic(path: Path = SYNTHETIC_PATH) -> list[dict]:
    return [
        _case(c["id"], "synthetic", c.get("contact", ""),
              [(d, who == "U", text) for d, who, text in c["messages"]], c.get("expect"))
        for c in yaml.safe_load(path.read_text(encoding="utf-8"))
    ]


def load_real(path: Path = REAL_PATH) -> list[dict]:
    if not path.is_file():
        return []
    return [
        _case(x["id"], "real", x.get("contact", ""),
              [("", bool(m.get("me")), m.get("text") or "") for m in x["messages"]], {})
        for x in json.loads(path.read_text(encoding="utf-8"))
    ]


def select_cases(
    which: str, provider: str, *, allow_cloud_real: bool = False,
    synthetic_path: Path = SYNTHETIC_PATH, real_path: Path = REAL_PATH,
) -> tuple[list[dict], list[str]]:
    """Cases to run for ``provider`` plus human notes about what was skipped (privacy)."""
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
                notes.append("real cases: none found (data/eval/contact_name_hint_real.json)")
            cases += real
    return cases, notes


def build_prompt(case: dict) -> str:
    from services.contact_names import build_hint_prompt

    return build_hint_prompt(case["contact"], [(me, t) for _, me, t in case["messages"]])


def score(case: dict, raw: dict | None) -> dict:
    """Score one answer (None = LLM failed/invalid) after the production validation."""
    from services.contact_names import validate_hint

    base = {"id": case["id"], "kind": case["kind"]}
    if raw is None:
        return base | {"valid": False, "ok": False, "fails": ["sem resposta"]}
    theirs = [t for _, me, t in case["messages"] if not me]
    hint = validate_hint(raw, theirs)
    if case["kind"] == "real":
        return base | {"valid": True, "ok": True, "fails": [], "hint": hint is not None}
    accepted = [norm(n) for n in case["expect"].get("nome") or []]
    got = norm(hint["nome"]) if hint else ""
    fails: list[str] = []
    if accepted and got not in accepted:
        fails.append(f"esperava {accepted}, veio {got or 'nada'}")
    if not accepted and hint:
        fails.append(f"não deveria sugerir, veio {got}")
    return base | {"valid": True, "ok": not fails, "fails": fails, "got": got}


def evaluate_case(case: dict, provider: str, models: list[str] | None) -> tuple[dict, float, float]:
    """(score row, seconds, cost_usd)."""
    from services import llm_structured
    from services.contact_names import HINT_SCHEMA

    t0 = time.perf_counter()
    before = _spent()
    raw = llm_structured.run_structured(
        "CONTACT_NAME_HINT", build_prompt(case), HINT_SCHEMA, provider=provider, models=models
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
        for _ in range(repeat):
            row, secs, c = evaluate_case(case, provider, models)
            rows.append(row)
            if secs:
                lat.append(secs)
            cost += c
    synth = [r for r in rows if r["kind"] == "synthetic"]
    real = [r for r in rows if r["kind"] == "real"]
    return {
        "rows": rows, "n": len(rows), "valid": _pct(rows, "valid"),
        "p50": _percentile(lat, 0.5), "p95": _percentile(lat, 0.95), "cost": cost,
        "synthetic": (sum(r["ok"] for r in synth), len(synth)),
        "synthetic_accuracy": _pct(synth, "ok") if synth else None,
        "real": (sum(r["ok"] for r in real), len(real)),
        "real_hints": sum(1 for r in real if r.get("hint")),
    }


def format_report(label: str, m: dict) -> list[str]:
    cost = f"US${m['cost']:.4f}" if m["cost"] else "n/a"
    ok, n = m["synthetic"]
    line = f"{label}: synthetic ok={ok}/{n}"
    if m["synthetic_accuracy"] is not None:
        line += f" accuracy={m['synthetic_accuracy']:.0%}"
    if m["real"][1]:
        line += f" real_valid={m['real'][0]}/{m['real'][1]} real_hints={m['real_hints']}"
    line += f" json={m['valid']:.0%} p50={m['p50']:.1f}s p95={m['p95']:.1f}s cost={cost}"
    lines = [line]
    for r in m["rows"]:
        if not r["ok"]:
            lines.append(f"   FAIL {r['id']}: {r['fails']}")  # never echo real-case content
    return lines


def _default_runs(provider: str) -> list[tuple[str, list[str] | None]]:
    from services import llm_structured

    prov, mods = llm_structured._resolve("CONTACT_NAME_HINT")
    if prov == provider and mods:
        return [(m, [m]) for m in mods]
    return [("default", None)]


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
    if not cases:
        out("no cases to run")
        return 1
    runs = [(m, [m]) for m in models] if models else _default_runs(provider)
    failed = False
    for label, mods in runs:
        m = run_model(cases, provider, mods, repeat)
        for line in format_report(f"{provider}:{label}", m):
            out(line)
        sa = m["synthetic_accuracy"]
        if sa is not None and sa < min_accuracy:
            out(f"GATE FAILED: synthetic accuracy {sa:.0%} < {min_accuracy:.0%} ({provider}:{label})")
            failed = True
    return 1 if failed else 0


def main(argv: list[str], cwd: str | None = None) -> int:
    """``llm-eval contact-name-hint ...`` (argv includes the target name)."""
    p = argparse.ArgumentParser(prog="evi-test llm-eval contact-name-hint")
    p.add_argument("target", choices=["contact-name-hint"])
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
