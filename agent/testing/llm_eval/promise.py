"""Promise-evaluation benchmark (prompt v4) against the real structured-LLM path.

    ./scripts/evi-test llm-eval promise [--provider openrouter|ollama|gemini]
        [--model M[,M2]] [--cases synthetic|real|all] [--repeat N]
        [--allow-cloud-real] [--min-accuracy 0.85]
    ./scripts/evi-test llm-eval-collect promise [--days N] [--chats N] [--import-prior PATH]

Synthetic cases (fictitious) live in ``tests/eval/promise_cases.yaml``. Real cases come
only from ``data/eval/promise_real.json`` (gitignored) and never leave the machine
unless the provider is local (ollama) or ``--allow-cloud-real`` is given for OpenRouter
(ZDR is enforced inside ``run_structured``). They are never sent to Gemini.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_PATH = REPO_ROOT / "tests" / "eval" / "promise_cases.yaml"
REAL_PATH = REPO_ROOT / "data" / "eval" / "promise_real.json"
MIN_ACCURACY = 0.85
SYNTHETIC_REF = (2026, 10, 12, 14, 0)  # Monday 14:00 local, as the YAML header says
AFTER_WINDOW = timedelta(minutes=30)
BEFORE_MAX = 10


def norm(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    ).lower()


def _load_env() -> None:
    """Fill missing env vars from the repo's .env (never overrides the process env)."""
    path = REPO_ROOT / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
    # The evaluator must not read/write the production spend table (and a DB host that is
    # unreachable from here would make run_structured fail closed): use the in-process counter.
    os.environ["DATABASE_URL"] = ""


# ---------------------------------------------------------------- cases


def _tz():
    from services.promise_context import _tz as tz

    return tz()


def _aware(ts: str | datetime) -> datetime:
    dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_tz())
    return dt.astimezone(_tz())


def _case(cid, kind, contact, ref, message, before, after, expect) -> dict:
    """before/after: lists of (datetime, from_me, text)."""
    return {
        "id": cid, "kind": kind, "contact": contact, "ref": ref, "message": message,
        "before": before, "after": after, "expect": expect or {},
    }


def load_synthetic(path: Path = SYNTHETIC_PATH) -> list[dict]:
    ref = datetime(*SYNTHETIC_REF, tzinfo=_tz())
    cases = []
    for c in yaml.safe_load(path.read_text(encoding="utf-8")):
        ctx = c.get("context") or []
        before = [
            (ref - timedelta(minutes=5 * (len(ctx) - i)), who == "U", text)
            for i, (who, text) in enumerate(ctx)
        ]
        after = [(ref + timedelta(minutes=m), who == "U", text) for who, text, m in c.get("after") or []]
        cases.append(_case(c["id"], "synthetic", c["contact"], ref, c["message"], before, after, c["expect"]))
    return cases


def load_real(path: Path = REAL_PATH) -> list[dict]:
    """Real cases; entries with an empty ``expect`` are unlabelled and not scored."""
    if not path.is_file():
        return []
    cases = []
    for x in json.loads(path.read_text(encoding="utf-8")):
        ref = _aware(x["ts"])

        def conv(items):
            return [(_aware(m["ts"]) if m.get("ts") else ref, bool(m.get("me")), m.get("text") or "") for m in items]

        before = conv(x.get("before") or [])[-BEFORE_MAX:]
        after = [m for m in conv(x.get("after") or []) if m[0] - ref <= AFTER_WINDOW]
        cases.append(_case(x["id"], "real", x["contact"], ref, x["message"], before, after, x.get("expect")))
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
                notes.append("real cases: none found (run llm-eval-collect promise)")
            cases += real
    return cases, notes


# ---------------------------------------------------------------- prompt + interpretation


def build_prompt(case: dict) -> str:
    from services.promise_context import _line, build_promise_prompt

    contact = case["contact"]
    before = [_line(ts, me, text, contact) for ts, me, text in case["before"]]
    after = [_line(ts, me, text, contact) for ts, me, text in case["after"]]
    ref = case["ref"]
    return build_promise_prompt(contact, before, case["message"], ref.strftime("%d/%m %H:%M"), after, ref)


def interpret(raw: dict, message_text: str, message_ts: datetime) -> dict:
    """Same post-processing as ``promise_context.evaluate_promise``, on a raw LLM dict."""
    from services.promise_context import PROMPT_VERSION, _local, _meaningful
    from services.whatsapp_processor import resolve_due

    ref = _local(message_ts)
    what = str(raw.get("what") or "").strip()
    is_promise = bool(raw.get("usuario_se_compromete")) and _meaningful(what)
    title = ""
    due = None
    if is_promise:
        title = (what[:1].upper() + what[1:])[:80]
        quando = str(raw.get("quando") or "").strip()
        due = resolve_due(quando, ref) if quando else resolve_due(message_text, ref)
    return {
        "is_promise": is_promise,
        "title": title,
        "due": due,
        "done": bool(raw.get("done")) if is_promise else False,
        "pedido": str(raw.get("pedido") or "").strip(),
        "prompt_version": PROMPT_VERSION,
    }


def score(case: dict, result: dict | None) -> dict:
    """Score one interpreted result (None = LLM failed) against ``case['expect']``."""
    exp = case["expect"]
    if result is None:
        store, title, due = False, "", None
        valid = False
    else:
        store = bool(result["is_promise"]) and not result["done"]
        title, due, valid = result["title"], result["due"], True
    want = bool(exp["store"])
    cls_ok = store == want
    what_ok = (not want) or (not store) or not exp.get("what") or any(k in norm(title) for k in exp["what"])
    due_ok = (not want) or (not store) or "due" not in exp or due == exp["due"]
    return {
        "id": case["id"], "kind": case["kind"], "valid": valid, "store": store, "expect": want,
        "title": title, "due": due, "cls_ok": cls_ok, "what_ok": what_ok, "due_ok": due_ok,
        "ok": cls_ok and what_ok and due_ok,
        "fp": store and not want, "fn": want and not store,
    }


# ---------------------------------------------------------------- run


def _spent() -> float:
    try:
        from services import llm_structured

        v = llm_structured._spent_today()
        return v if math.isfinite(v) else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def evaluate_case(case: dict, provider: str, models: list[str] | None) -> tuple[dict, float, float]:
    """(score row, seconds, cost_usd). The detect_promise prefilter mirrors production."""
    from services import llm_structured
    from services.promise_context import PROMISE_SCHEMA
    from services.promises import detect_promise

    t0 = time.perf_counter()
    cost = 0.0
    if not detect_promise(case["message"]):
        return score(case, interpret({}, case["message"], case["ref"])), 0.0, 0.0
    before_cost = _spent()
    raw = llm_structured.run_structured(
        "promise", build_prompt(case), PROMISE_SCHEMA, provider=provider, models=models
    )
    cost = max(0.0, _spent() - before_cost)
    secs = time.perf_counter() - t0
    result = interpret(raw, case["message"], case["ref"]) if isinstance(raw, dict) else None
    return score(case, result), secs, cost


def _pct(rows: list[dict], key: str) -> float:
    return sum(1 for r in rows if r[key]) / len(rows) if rows else 0.0


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(p * len(s)) - 1))]


def run_model(cases: list[dict], provider: str, models: list[str] | None, repeat: int = 1) -> dict:
    rows: list[dict] = []
    lat: list[float] = []
    cost = 0.0
    for case in cases:
        if not case["expect"]:
            continue  # unlabelled real case
        for _ in range(repeat):
            row, secs, c = evaluate_case(case, provider, models)
            rows.append(row)
            if secs:
                lat.append(secs)
            cost += c
    synth = [r for r in rows if r["kind"] == "synthetic"]
    return {
        "rows": rows, "n": len(rows), "accuracy": _pct(rows, "cls_ok"), "overall": _pct(rows, "ok"),
        "title": _pct(rows, "what_ok"), "due": _pct(rows, "due_ok"), "valid": _pct(rows, "valid"),
        "fp": sum(r["fp"] for r in rows), "fn": sum(r["fn"] for r in rows),
        "p50": _percentile(lat, 0.5), "p95": _percentile(lat, 0.95), "cost": cost,
        "synthetic_accuracy": _pct(synth, "cls_ok") if synth else None,
    }


def format_report(label: str, m: dict) -> list[str]:
    cost = f"US${m['cost']:.4f}" if m["cost"] else "n/a"
    lines = [
        f"{label}: n={m['n']} accuracy={m['accuracy']:.0%} (full match {m['overall']:.0%}) "
        f"title={m['title']:.0%} due={m['due']:.0%} json={m['valid']:.0%} FP={m['fp']} FN={m['fn']} "
        f"p50={m['p50']:.1f}s p95={m['p95']:.1f}s cost={cost}"
    ]
    for r in m["rows"]:
        if r["ok"]:
            continue
        flags = f"store={r['store']} expect={r['expect']} title_ok={r['what_ok']} due_ok={r['due_ok']}"
        if r["kind"] == "synthetic":  # never echo real-case content
            flags += f" title={r['title']!r} due={r['due']}"
        lines.append(f"   FAIL {r['id']}: {flags}")
    return lines


def _default_run(provider: str) -> tuple[str, list[str] | None]:
    """Configured chain for the task when ``provider`` is the configured one (else provider default)."""
    from services import llm_structured

    prov, mods = llm_structured._resolve("PROMISE")
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
    labelled = [c for c in cases if c["expect"]]
    if len(labelled) < len(cases):
        out(f"note: {len(cases) - len(labelled)} unlabelled real case(s) not scored")
    if not labelled:
        out("no labelled cases to run")
        return 1
    runs = [(m, [m]) for m in models] if models else [_default_run(provider)]
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


# ---------------------------------------------------------------- collect / import


def import_prior(src: Path, dest: Path = REAL_PATH) -> tuple[int, int]:
    """Convert the prior benchmark format into ``dest``. Returns (converted, skipped).

    ``src`` is the directory (or its ``real_promises.json``) holding ``real_promises.json``,
    ``real_labels.yaml`` and, for ``R..`` labels, ``real_scan.json``.
    """
    base = src.parent if src.is_file() else src
    labels = yaml.safe_load((base / "real_labels.yaml").read_text(encoding="utf-8")) or {}
    pool: dict[str, dict] = {}
    scan = base / "real_scan.json"
    if scan.is_file():
        pool.update({f"R{i:02d}": x for i, x in enumerate(json.loads(scan.read_text(encoding="utf-8")))})
    stored = json.loads((base / "real_promises.json").read_text(encoding="utf-8"))
    pool.update({f"P{x['id']}": x for x in stored if x.get("found")})
    cases, skipped = [], 0
    for cid, exp in labels.items():
        x = pool.get(cid)
        if x is None:
            skipped += 1
            continue
        cases.append({
            "id": cid, "contact": x["contact"], "message": x["message"], "ts": x["ts"],
            "before": [{"ts": m.get("ts"), "me": bool(m.get("me")), "text": m.get("text") or ""}
                       for m in (x.get("context") or [])[-BEFORE_MAX:]],
            "after": [{"ts": m.get("ts"), "me": bool(m.get("me")), "text": m.get("text") or ""}
                      for m in (x.get("after") or [])],
            "expect": exp,
        })
    _write_real(dest, cases)
    return len(cases), skipped


def _write_real(dest: Path, cases: list[dict]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass


def collect(days: int = 30, chats: int = 50, dest: Path = REAL_PATH, out: Callable[[str], None] = print) -> int:
    """Append unlabelled candidate cases from recent fromMe promises (Evolution). Counts only."""
    from messaging.evolution import EvolutionClient
    from services.evolution_client import is_evi_bot_message
    from services.evolution_discovery import fetch_evolution_chats
    from services.evolution_parser import parse_evolution_message_list
    from services.promises import detect_promise

    try:
        chat_rows = fetch_evolution_chats(limit=chats)
    except Exception:  # noqa: BLE001
        chat_rows = []
    if not chat_rows:
        out("error: Evolution unreachable or returned no chats")
        return 1
    client = EvolutionClient()
    cutoff = datetime.now(_tz()) - timedelta(days=days)
    existing = json.loads(dest.read_text(encoding="utf-8")) if dest.is_file() else []
    known = {c["id"] for c in existing}
    added, scanned = 0, 0
    for chat in chat_rows:
        jid = chat["jid"]
        if jid.endswith("@g.us") or jid.endswith("@broadcast"):
            continue
        raw = client.find_messages(jid)
        if raw is None:
            continue
        msgs = []
        for m in parse_evolution_message_list(raw, remote_jid=jid):
            text = (m.text or "").strip()
            if text and m.ts and not is_evi_bot_message(text):
                try:
                    msgs.append((_aware(m.ts), m, text))
                except ValueError:
                    continue
        msgs.sort(key=lambda r: r[0])
        scanned += 1
        for i, (ts, m, text) in enumerate(msgs):
            cid = f"C-{m.id}"
            if not m.from_me or ts < cutoff or cid in known or not detect_promise(text):
                continue
            before = [x for x in msgs[:i] if ts - timedelta(hours=24) <= x[0]][-BEFORE_MAX:]
            after = [x for x in msgs[i + 1:] if x[0] - ts <= AFTER_WINDOW]
            existing.append({
                "id": cid, "contact": chat.get("label") or "contato", "message": text, "ts": ts.isoformat(),
                "before": [{"ts": x[0].isoformat(), "me": x[1].from_me, "text": x[2]} for x in before],
                "after": [{"ts": x[0].isoformat(), "me": x[1].from_me, "text": x[2]} for x in after],
                "expect": {},
            })
            known.add(cid)
            added += 1
    _write_real(dest, existing)
    out(f"scanned {scanned} chat(s); added {added} unlabelled case(s); total {len(existing)} in data/eval/")
    return 0


# ---------------------------------------------------------------- CLI entry points


def main(argv: list[str], cwd: str | None = None) -> int:
    """``llm-eval promise ...`` (argv excludes the feature name)."""
    p = argparse.ArgumentParser(prog="evi-test llm-eval promise")
    p.add_argument("target", choices=["promise"])
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


def main_collect(argv: list[str], cwd: str | None = None) -> int:
    """``llm-eval-collect promise ...``."""
    p = argparse.ArgumentParser(prog="evi-test llm-eval-collect promise")
    p.add_argument("target", choices=["promise"])
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--chats", type=int, default=50)
    p.add_argument("--import-prior", default="")
    try:
        a = p.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 2)
    _load_env()
    if a.import_prior:
        src = Path(a.import_prior)
        if not src.is_absolute() and cwd:
            src = Path(cwd) / src
        try:
            n, skipped = import_prior(src)
        except (OSError, KeyError, ValueError) as exc:
            print(f"error: import failed ({type(exc).__name__})")
            return 1
        print(f"imported {n} case(s), skipped {skipped}")
        return 0
    return collect(days=a.days, chats=a.chats)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
