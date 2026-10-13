"""Offline tests for the promise LLM evaluator (fake run_structured, fictitious data)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from services import llm_structured
from testing.llm_eval import promise as ev


def _llm(promise: bool, what: str = "", quando: str = "", done: bool = False) -> dict:
    return {"pedido": "", "usuario_se_compromete": promise, "what": what, "quando": quando, "done": done}


def _case(expect: dict, message: str = "te mando a proposta amanhã", kind: str = "synthetic") -> dict:
    ref = datetime(2026, 10, 12, 14, 0, tzinfo=ev._tz())
    return ev._case("T1", kind, "Ana", ref, message, [], [], expect)


# ---------------------------------------------------------------- scoring


def test_interpret_matches_evaluate_promise_rules():
    ref = datetime(2026, 10, 12, 14, 0, tzinfo=ev._tz())
    out = ev.interpret(_llm(True, "mandar a proposta", "amanhã"), "x", ref)
    assert out["is_promise"] and out["title"] == "Mandar a proposta" and out["due"] == "2026-10-13"
    assert ev.interpret(_llm(True, "avisar"), "x", ref)["is_promise"] is False  # generic verb
    assert ev.interpret(_llm(False), "x", ref)["title"] == ""


def test_score_true_positive_with_keywords_and_due():
    case = _case({"store": True, "what": ["proposta"], "due": "2026-10-13"})
    res = ev.interpret(_llm(True, "Mandar a PROPOSTA", "amanhã"), case["message"], case["ref"])
    row = ev.score(case, res)
    assert row["ok"] and not row["fp"] and not row["fn"]


def test_title_keywords_are_accent_insensitive():
    case = _case({"store": True, "what": ["orcamento"]})
    res = ev.interpret(_llm(True, "Mandar o orçamento"), case["message"], case["ref"])
    assert ev.score(case, res)["what_ok"]
    bad = ev.interpret(_llm(True, "Mandar a fatura"), case["message"], case["ref"])
    row = ev.score(case, bad)
    assert not row["what_ok"] and row["cls_ok"] and not row["ok"]


def test_wrong_due_fails():
    case = _case({"store": True, "what": ["proposta"], "due": "2026-10-14"})
    res = ev.interpret(_llm(True, "Mandar a proposta", "amanhã"), case["message"], case["ref"])
    row = ev.score(case, res)
    assert not row["due_ok"] and not row["ok"]


def test_false_positive_and_false_negative():
    fp = ev.score(_case({"store": False}), ev.interpret(_llm(True, "Mandar x"), "m", datetime(2026, 10, 12, tzinfo=ev._tz())))
    assert fp["fp"] and not fp["fn"] and not fp["ok"]
    fn = ev.score(_case({"store": True}), ev.interpret(_llm(False), "m", datetime(2026, 10, 12, tzinfo=ev._tz())))
    assert fn["fn"] and not fn["fp"]


def test_done_promise_is_not_stored():
    case = _case({"store": False})
    res = ev.interpret(_llm(True, "Passar o contato", done=True), case["message"], case["ref"])
    assert ev.score(case, res)["ok"]


def test_llm_failure_counts_as_invalid_not_stored():
    row = ev.score(_case({"store": True}), None)
    assert not row["valid"] and row["fn"]


# ---------------------------------------------------------------- loading


def test_synthetic_yaml_loads_30_cases():
    cases = ev.load_synthetic()
    assert len(cases) == 30
    assert len({c["id"] for c in cases}) == 30
    assert all("store" in c["expect"] for c in cases)
    assert all(c["kind"] == "synthetic" for c in cases)


def test_build_prompt_is_v4_with_context():
    case = next(c for c in ev.load_synthetic() if c["id"].startswith("S01"))
    prompt = ev.build_prompt(case)
    assert "usuario_se_compromete" in prompt and "Pode deixar" in prompt and "orçamento até sexta" in prompt


# ---------------------------------------------------------------- privacy


def _real_file(tmp_path, expect=None) -> Path:
    path = tmp_path / "real.json"
    path.write_text(json.dumps([{
        "id": "R1", "contact": "Zeca", "message": "te mando a planilha amanhã", "ts": "2026-10-12T14:00:00-03:00",
        "before": [{"ts": "2026-10-12T13:55:00-03:00", "me": False, "text": "manda a planilha?"}],
        "after": [], "expect": expect if expect is not None else {"store": True, "what": ["planilha"]},
    }]))
    return path


def test_gemini_never_gets_real_cases(tmp_path):
    cases, notes = ev.select_cases("all", "gemini", allow_cloud_real=True, real_path=_real_file(tmp_path))
    assert {c["kind"] for c in cases} == {"synthetic"}
    assert "real cases skipped (gemini)" in notes


def test_openrouter_real_requires_flag(tmp_path):
    path = _real_file(tmp_path)
    cases, notes = ev.select_cases("all", "openrouter", real_path=path)
    assert {c["kind"] for c in cases} == {"synthetic"} and any("skipped" in n for n in notes)
    cases, _ = ev.select_cases("all", "openrouter", allow_cloud_real=True, real_path=path)
    assert "real" in {c["kind"] for c in cases}


def test_ollama_runs_real_cases(tmp_path):
    cases, _ = ev.select_cases("real", "ollama", real_path=_real_file(tmp_path))
    assert [c["kind"] for c in cases] == ["real"]


def test_gemini_run_never_calls_llm_with_real_prompt(monkeypatch, tmp_path):
    seen: list[str] = []

    def fake(task, prompt, schema, **kw):
        seen.append(prompt)
        return _llm(False)

    monkeypatch.setattr(llm_structured, "run_structured", fake)
    out: list[str] = []
    ev.run("all", "gemini", ["m"], real_path=_real_file(tmp_path), out=out.append, min_accuracy=0.0)
    assert seen and not any("planilha" in p for p in seen)
    assert any("real cases skipped (gemini)" in line for line in out)


# ---------------------------------------------------------------- run + gate


def _oracle(monkeypatch, correct: bool):
    """Fake LLM answering from the YAML expectations (or always the opposite)."""
    by_prompt = {ev.build_prompt(c): c["expect"] for c in ev.load_synthetic()}

    def fake(task, prompt, schema, *, provider=None, models=None):
        assert task == "promise" and provider == "openrouter"
        exp = by_prompt[prompt]
        promise = exp["store"] == correct
        return _llm(promise, (exp.get("what") or ["tarefa"])[0] if promise else "")

    monkeypatch.setattr(llm_structured, "run_structured", fake)


def test_threshold_gate_fails_below_min_accuracy(monkeypatch):
    _oracle(monkeypatch, correct=False)
    out: list[str] = []
    assert ev.run("synthetic", "openrouter", ["m1"], out=out.append) == 1
    assert any("GATE FAILED" in line for line in out)
    assert any(line.lstrip().startswith("FAIL") for line in out)  # failed cases are listed


def test_threshold_gate_passes_and_min_accuracy_is_overridable(monkeypatch):
    _oracle(monkeypatch, correct=True)
    out: list[str] = []
    rc = ev.run("synthetic", "openrouter", ["m1"], out=out.append)
    report = [line for line in out if line.startswith("openrouter:m1")]
    assert report and "accuracy=" in report[0] and "p50=" in report[0]
    assert rc == 0, out
    _oracle(monkeypatch, correct=False)
    assert ev.run("synthetic", "openrouter", ["m1"], min_accuracy=0.0, out=lambda _s: None) == 0


def test_main_exit_code_and_flags(monkeypatch):
    _oracle(monkeypatch, correct=False)
    assert ev.main(["promise", "--model", "a,b", "--min-accuracy", "0.0"]) == 0
    assert ev.main(["promise", "--model", "a", "--min-accuracy", "0.99"]) == 1


# ---------------------------------------------------------------- import-prior


def test_import_prior_converts_formats(tmp_path):
    src = tmp_path / "prior"
    src.mkdir()
    (src / "real_scan.json").write_text(json.dumps([
        {"chat": "x", "contact": "Bia", "message": "te mando o link", "ts": "2026-10-09T11:50:04+00:00",
         "context": [{"ts": "2026-10-09T11:45:30+00:00", "me": False, "text": "manda o link?"}],
         "after": [{"ts": "2026-10-09T11:52:00+00:00", "me": True, "text": "pronto"},
                   {"ts": "2026-10-09T13:52:00+00:00", "me": True, "text": "tarde demais"}]},
    ]))
    (src / "real_promises.json").write_text(json.dumps([
        {"id": 48, "contact": "Caio", "message": "já te falo", "ts": "2026-10-09 11:50:04.242625+00",
         "context": [], "after": [], "found": True},
        {"id": 49, "contact": "Dani", "message": "x", "ts": "2026-10-09T11:50:04+00:00",
         "context": [], "after": [], "found": False},
    ]))
    (src / "real_labels.yaml").write_text(yaml.safe_dump({
        "R00": {"store": True, "what": ["link"]}, "P48": {"store": False}, "P49": {"store": False},
    }))
    dest = tmp_path / "out" / "promise_real.json"
    n, skipped = ev.import_prior(src, dest)
    assert (n, skipped) == (2, 1)  # P49 was not found
    data = json.loads(dest.read_text())
    assert {c["id"] for c in data} == {"R00", "P48"}
    cases = ev.load_real(dest)
    r00 = next(c for c in cases if c["id"] == "R00")
    assert r00["expect"] == {"store": True, "what": ["link"]}
    assert len(r00["before"]) == 1 and len(r00["after"]) == 1  # 30 min window applied at load
    assert next(c for c in cases if c["id"] == "P48")["expect"] == {"store": False}
