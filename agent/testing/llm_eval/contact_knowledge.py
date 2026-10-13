"""Contact-knowledge benchmark (prompt ``knowledge-v1``) against the real structured-LLM path.

    ./scripts/evi-test llm-eval contact-knowledge [--provider openrouter|ollama|gemini]
        [--model M[,M2]] [--cases synthetic|real|all] [--repeat N]
        [--allow-cloud-real] [--min-accuracy 0.85]

Synthetic cases (fictitious) live in ``tests/eval/contact_knowledge_cases.yaml``. Real cases
come only from ``data/eval/contact_knowledge_real.json`` (gitignored, mode 0600) and follow
the same privacy matrix as the promise evaluator: never sent to Gemini, sent to OpenRouter
only with ``--allow-cloud-real`` (ZDR is enforced inside ``run_structured``), always to
ollama. Real cases have no labels: they are scored structurally (valid JSON, no metadata in
facts, no injection-looking entry accepted) and their content is never printed.
The prompt and the validation are the production ones (``contact_knowledge``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable

import yaml

from testing.llm_eval.promise import (
    REPO_ROOT,
    _aware,
    _load_env,
    _percentile,
    _spent,
    _write_real,
    norm,
)

SYNTHETIC_PATH = REPO_ROOT / "tests" / "eval" / "contact_knowledge_cases.yaml"
REAL_PATH = REPO_ROOT / "data" / "eval" / "contact_knowledge_real.json"
MIN_ACCURACY = 0.85
SYNTHETIC_TODAY = "2026-10-12"
META_WORDS = ("jid", "created", "knowledge_updated", "criado em", "metadado")


# ---------------------------------------------------------------- cases


def _case(cid, kind, contact, facts, items, messages, expect) -> dict:
    """messages: list of (YYYY-MM-DD, from_me, text)."""
    return {
        "id": cid, "kind": kind, "contact": contact, "facts": facts, "open": items,
        "messages": messages, "dates": {d for d, _, _ in messages}, "expect": expect or {},
    }


def load_synthetic(path: Path = SYNTHETIC_PATH) -> list[dict]:
    cases = []
    for c in yaml.safe_load(path.read_text(encoding="utf-8")):
        msgs = [(d, who == "U", text) for d, who, text in c["messages"]]
        cases.append(_case(
            c["id"], "synthetic", c["contact"],
            [tuple(f) for f in c.get("facts") or []], [tuple(o) for o in c.get("open") or []],
            msgs, c.get("expect"),
        ))
    return cases


def load_real(path: Path = REAL_PATH) -> list[dict]:
    if not path.is_file():
        return []
    cases = []
    for x in json.loads(path.read_text(encoding="utf-8")):
        msgs = [
            (_aware(m["ts"]).strftime("%Y-%m-%d"), bool(m.get("me")), m.get("text") or "")
            for m in x["messages"]
        ]
        cases.append(_case(x["id"], "real", x["contact"], [], [], msgs, {}))
    return cases


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
                notes.append("real cases: none found (data/eval/contact_knowledge_real.json)")
            cases += real
    return cases, notes


# ---------------------------------------------------------------- prompt + scoring


def build_prompt(case: dict) -> str:
    from services.contact_knowledge import build_knowledge_prompt

    return build_knowledge_prompt(
        case["contact"], case["facts"], case["open"], case["messages"], SYNTHETIC_TODAY
    )


def interpret(case: dict, raw: dict) -> tuple[list[str], list[str], dict]:
    """Final fact/open texts after the production validation, plus its counts."""
    from services.contact_knowledge import Fact, Item, Profile, apply_update

    prof = Profile(
        facts=[Fact(t, d) for t, d in case["facts"]],
        open_items=[Item(t, d) for t, d in case["open"]],
    )
    users = [t for _, me, t in case["messages"] if me]
    facts, items, counts = apply_update(prof, raw, case["dates"], SYNTHETIC_TODAY, users)
    return [f.text for f in facts], [i.text for i in items], counts


def score(case: dict, raw: dict | None) -> dict:
    """Score one answer (None = LLM failed/invalid) against ``case['expect']``."""
    base = {"id": case["id"], "kind": case["kind"]}
    if raw is None:
        return base | {"valid": False, "ok": False, "fails": ["sem resposta"], "dropped": 0}
    facts, opened, counts = interpret(case, raw)
    dropped = len(raw.get("add") or []) - counts["added"]
    ftxt, otxt = norm(" | ".join(facts)), norm(" | ".join(opened))
    fails: list[str] = []
    exp = case["expect"]
    if case["kind"] == "real":
        both = ftxt + " | " + otxt
        if any(w in both for w in META_WORDS):
            fails.append("metadata")
        from services.contact_knowledge import is_injection

        users = [t for _, me, t in case["messages"] if me]
        if any(is_injection(t, users) for t in facts + opened):
            fails.append("injection")
        return base | {"valid": True, "ok": not fails, "fails": fails, "dropped": dropped}
    for g in exp.get("facts", []):
        if not any(k in ftxt for k in g):
            fails.append(f"falta fato {g}")
    for g in exp.get("open", []):
        if not any(k in otxt for k in g):
            fails.append(f"falta aberto {g}")
    for k in exp.get("forbid", []):
        if k in ftxt or k in otxt:
            fails.append(f"proibido {k}")
    for k in exp.get("forbid_facts", []):
        if k in ftxt:
            fails.append(f"fato proibido {k}")
    for k in exp.get("forbid_open", []):
        if k in otxt:
            fails.append(f"aberto proibido {k}")
    if "max_facts" in exp and len(facts) > exp["max_facts"]:
        fails.append(f"{len(facts)} fatos")
    if "max_open" in exp and len(opened) > exp["max_open"]:
        fails.append(f"{len(opened)} abertos")
    return base | {
        "valid": True, "ok": not fails, "fails": fails, "dropped": dropped,
        "facts": facts, "open": opened,
    }


# ---------------------------------------------------------------- run


def evaluate_case(case: dict, provider: str, models: list[str] | None) -> tuple[dict, float, float]:
    """(score row, seconds, cost_usd)."""
    from services import llm_structured
    from services.contact_knowledge import KNOWLEDGE_SCHEMA

    t0 = time.perf_counter()
    before = _spent()
    raw = llm_structured.run_structured(
        "CONTACT_KNOWLEDGE", build_prompt(case), KNOWLEDGE_SCHEMA, provider=provider, models=models
    )
    cost = max(0.0, _spent() - before)
    secs = time.perf_counter() - t0
    return score(case, raw if isinstance(raw, dict) else None), secs, cost


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
        "dropped": sum(r["dropped"] for r in rows),
        "p50": _percentile(lat, 0.5), "p95": _percentile(lat, 0.95), "cost": cost,
        "synthetic": (sum(r["ok"] for r in synth), len(synth)),
        "synthetic_accuracy": _pct(synth, "ok") if synth else None,
        "real": (sum(r["ok"] for r in real), len(real)),
    }


def format_report(label: str, m: dict) -> list[str]:
    cost = f"US${m['cost']:.4f}" if m["cost"] else "n/a"
    ok, n = m["synthetic"]
    line = f"{label}: synthetic ok={ok}/{n}"
    if m["synthetic_accuracy"] is not None:
        line += f" accuracy={m['synthetic_accuracy']:.0%}"
    rok, rn = m["real"]
    if rn:
        line += f" real_structural_ok={rok}/{rn}"
    line += (f" json={m['valid']:.0%} dropped(no evidence)={m['dropped']} "
             f"p50={m['p50']:.1f}s p95={m['p95']:.1f}s cost={cost}")
    lines = [line]
    for r in m["rows"]:
        if r["ok"]:
            continue
        detail = f" {r['fails']} F={r.get('facts')} O={r.get('open')}" if r["kind"] == "synthetic" else (
            f" {r['fails']}")  # never echo real-case content
        lines.append(f"   FAIL {r['id']}:{detail}")
    return lines


def _default_runs(provider: str) -> list[tuple[str, list[str] | None]]:
    """One run per configured model of the task (when ``provider`` is the configured one)."""
    from services import llm_structured

    prov, mods = llm_structured._resolve("CONTACT_KNOWLEDGE")
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


# ---------------------------------------------------------------- import / CLI


def import_prior(src: Path, dest: Path = REAL_PATH) -> int:
    """Copy the prior benchmark's ``real_knowledge.json`` (id, contact, messages[ts, me, text])."""
    data = json.loads(src.read_text(encoding="utf-8"))
    cases = [
        {"id": x["id"], "contact": x["contact"],
         "messages": [{"ts": m["ts"], "me": bool(m.get("me")), "text": m.get("text") or ""} for m in x["messages"]]}
        for x in data
    ]
    _write_real(dest, cases)
    return len(cases)


def main(argv: list[str], cwd: str | None = None) -> int:
    """``llm-eval contact-knowledge ...`` (argv includes the target name)."""
    p = argparse.ArgumentParser(prog="evi-test llm-eval contact-knowledge")
    p.add_argument("target", choices=["contact-knowledge"])
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
