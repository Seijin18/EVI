"""Offline tests for the promise LLM evaluator (fake run_structured, fictitious data)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from services import llm_structured
from testing.llm_eval import promise as ev


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """The evaluator CLI loads .env into os.environ; keep that out of other tests."""
    import os

    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


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


# ---------------------------------------------------------------- contact-knowledge evaluator

from testing.llm_eval import contact_knowledge as kev  # noqa: E402


def _kn_oracle(monkeypatch, correct: bool):
    """Fake CONTACT_KNOWLEDGE LLM answering from YAML expectations (or breaking them)."""
    by_prompt = {kev.build_prompt(c): c for c in kev.load_synthetic()}

    def fake(task, prompt, schema, *, provider=None, models=None):
        assert task == "CONTACT_KNOWLEDGE" and provider == "openrouter"
        c = by_prompt[prompt]
        exp = c["expect"]
        day = sorted(c["dates"])[0]
        if not correct:
            # invent a fact for every case: breaks max_facts/forbid/expect.facts of most cases
            return {"add": [{"fact": "deve R$ 5000 e tem reunião", "date": day}], "remove": [], "open": []}
        add = [{"fact": g[0], "date": day} for g in exp.get("facts", [])]
        opened = [{"item": g[0], "date": day} for g in exp.get("open", [])]
        remove = [f"F{i}" for i in range(1, len(c["facts"]) + 1)] if exp.get("forbid_facts") else []
        return {"add": add, "remove": remove, "open": opened}

    monkeypatch.setattr(llm_structured, "run_structured", fake)


def test_knowledge_synthetic_yaml_loads_8_cases():
    cases = kev.load_synthetic()
    assert len(cases) == 8
    assert all(c["messages"] and c["expect"] is not None for c in cases)


def test_knowledge_gate_passes_with_oracle(monkeypatch):
    _kn_oracle(monkeypatch, correct=True)
    out: list[str] = []
    rc = kev.run("synthetic", "openrouter", ["m1"], out=out.append)
    assert rc == 0, out
    assert any(l.startswith("openrouter:m1: synthetic ok=8/8") for l in out)


def test_knowledge_gate_fails_below_min_accuracy(monkeypatch):
    _kn_oracle(monkeypatch, correct=False)
    out: list[str] = []
    assert kev.run("synthetic", "openrouter", ["m1"], out=out.append) == 1
    assert any("GATE FAILED" in l for l in out) and any(l.lstrip().startswith("FAIL") for l in out)
    assert kev.run("synthetic", "openrouter", ["m1"], min_accuracy=0.0, out=lambda _s: None) == 0


def test_knowledge_invalid_answer_counts_as_failure(monkeypatch):
    monkeypatch.setattr(llm_structured, "run_structured", lambda *a, **k: None)
    out: list[str] = []
    assert kev.run("synthetic", "openrouter", ["m1"], out=out.append) == 1
    assert "json=0%" in out[0]


def test_knowledge_report_is_per_model(monkeypatch):
    _kn_oracle(monkeypatch, correct=True)
    out: list[str] = []
    kev.run("synthetic", "openrouter", ["m1", "m2"], out=out.append)
    assert [l.split(":")[1] for l in out if l.startswith("openrouter:")] == ["m1", "m2"]


def test_knowledge_main_exit_code_and_flags(monkeypatch):
    _kn_oracle(monkeypatch, correct=False)
    assert kev.main(["contact-knowledge", "--model", "a", "--min-accuracy", "0.0"]) == 0
    assert kev.main(["contact-knowledge", "--model", "a", "--min-accuracy", "0.99"]) == 1


def test_cli_dispatches_contact_knowledge_and_promise(monkeypatch):
    from testing import cli

    seen = []
    monkeypatch.setattr(kev, "main", lambda argv, cwd=None: seen.append(("ck", argv)) or 0)
    monkeypatch.setattr(ev, "main", lambda argv, cwd=None: seen.append(("promise", argv)) or 0)
    assert cli.run_llm_eval(["contact-knowledge", "--cases", "synthetic"], ".") is True
    assert cli.run_llm_eval(["promise"], ".") is True
    assert [s[0] for s in seen] == ["ck", "promise"]


def _kn_real_file(tmp_path) -> Path:
    p = tmp_path / "real.json"
    p.write_text(json.dumps([{"id": "R1", "contact": "Bia", "messages": [
        {"ts": "2026-10-11T12:00:00+00:00", "me": False, "text": "moro em Recife desde 2020"},
        {"ts": "2026-10-11T12:01:00+00:00", "me": True, "text": "legal"},
    ]}]))
    return p


def test_knowledge_privacy_matrix(tmp_path):
    p = _kn_real_file(tmp_path)
    assert not [c for c in kev.select_cases("all", "gemini", real_path=p)[0] if c["kind"] == "real"]
    assert not [c for c in kev.select_cases("all", "openrouter", real_path=p)[0] if c["kind"] == "real"]
    assert [c for c in kev.select_cases("all", "openrouter", allow_cloud_real=True, real_path=p)[0] if c["kind"] == "real"]
    assert [c for c in kev.select_cases("real", "ollama", real_path=p)[0] if c["kind"] == "real"]


def test_knowledge_real_structural_scoring_never_echoes_content(monkeypatch, tmp_path):
    p = _kn_real_file(tmp_path)
    secret_fact = "Mora em Recife"
    monkeypatch.setattr(
        llm_structured, "run_structured",
        lambda *a, **k: {"add": [{"fact": secret_fact, "date": "2026-10-11"},
                                 {"fact": "Deve R$ 900 a ele", "date": "2026-10-11"},
                                 {"fact": "sem data", "date": ""}], "remove": [], "open": []},
    )
    out: list[str] = []
    rc = kev.run("real", "ollama", ["m"], out=out.append, real_path=p)
    assert rc == 0, out  # no synthetic cases => no gate
    text = "\n".join(out)
    assert "real_structural_ok=1/1" in text and "dropped(no evidence)=2" in text
    assert "Recife" not in text and "R$" not in text

    monkeypatch.setattr(
        llm_structured, "run_structured",
        lambda *a, **k: {"add": [{"fact": "criado em 2026", "date": "2026-10-11"}], "remove": [], "open": []},
    )
    out.clear()
    kev.run("real", "ollama", ["m"], out=out.append, real_path=p)
    assert "real_structural_ok=0/1" in "\n".join(out) and "metadata" in "\n".join(out)


def test_knowledge_import_prior(tmp_path):
    src = _kn_real_file(tmp_path)
    dest = tmp_path / "out" / "contact_knowledge_real.json"
    assert kev.import_prior(src, dest) == 1
    assert [c["id"] for c in kev.load_real(dest)] == ["R1"]
    assert oct(dest.stat().st_mode & 0o777) == "0o600"


# ---------------------------------------------------------------- contact-name-hint evaluator

from testing.llm_eval import contact_name_hint as nev  # noqa: E402


def _nh_oracle(monkeypatch, correct: bool):
    """Fake CONTACT_NAME_HINT LLM answering from YAML expectations (or always hallucinating)."""
    by_prompt = {nev.build_prompt(c): c for c in nev.load_synthetic()}

    def fake(task, prompt, schema, *, provider=None, models=None):
        assert task == "CONTACT_NAME_HINT" and provider == "openrouter"
        c = by_prompt[prompt]
        if not correct:
            return {"nome": "Paulo", "evidencia": "sou o Paulo"}
        names = c["expect"].get("nome") or []
        if not names:
            return {"nome": "", "evidencia": ""}
        for _, me, text in c["messages"]:
            if not me and names[0] in text.casefold():
                i = text.casefold().index(names[0])
                return {"nome": text[i:i + len(names[0])], "evidencia": text[max(0, i - 6):i + len(names[0])]}
        raise AssertionError(c["id"])

    monkeypatch.setattr(llm_structured, "run_structured", fake)


def test_name_hint_yaml_has_enough_cases_incl_negatives():
    cases = nev.load_synthetic()
    assert len(cases) >= 8
    assert sum(1 for c in cases if not c["expect"]["nome"]) >= 4


def test_name_hint_gate_passes_with_oracle(monkeypatch):
    _nh_oracle(monkeypatch, correct=True)
    out: list[str] = []
    assert nev.run("synthetic", "openrouter", ["m1"], out=out.append) == 0, out
    assert any(" accuracy=100%" in l for l in out)


def test_name_hint_hallucinations_fail_the_gate(monkeypatch):
    _nh_oracle(monkeypatch, correct=False)
    out: list[str] = []
    assert nev.run("synthetic", "openrouter", ["m1"], out=out.append) == 1
    assert any("GATE FAILED" in l for l in out)


def test_name_hint_no_answer_is_failure(monkeypatch):
    monkeypatch.setattr(llm_structured, "run_structured", lambda *a, **k: None)
    out: list[str] = []
    assert nev.run("synthetic", "openrouter", ["m1"], out=out.append) == 1
    assert "json=0%" in out[0]


def test_name_hint_real_cases_privacy_matrix(tmp_path):
    real = tmp_path / "r.json"
    real.write_text('[{"id": "r1", "messages": [{"me": false, "text": "sou o Fulano"}]}]')
    _, notes = nev.select_cases("real", "openrouter", real_path=real)
    assert "skipped" in notes[0]
    assert nev.select_cases("real", "gemini", allow_cloud_real=True, real_path=real)[0] == []
    assert len(nev.select_cases("real", "openrouter", allow_cloud_real=True, real_path=real)[0]) == 1
    assert len(nev.select_cases("real", "ollama", real_path=real)[0]) == 1


def test_cli_dispatches_contact_name_hint(monkeypatch):
    from testing import cli

    seen = []
    monkeypatch.setattr(nev, "main", lambda argv, cwd=None: seen.append(argv) or 0)
    assert cli.run_llm_eval(["contact-name-hint", "--cases", "synthetic"], ".") is True
    assert seen == [["contact-name-hint", "--cases", "synthetic"]]


# ---------------------------------------------------------------- debt judge eval

from testing.llm_eval import debt as dv  # noqa: E402


def test_debt_yaml_loads_and_is_balanced():
    cases = dv.load_synthetic()
    assert len(cases) >= 24
    assert len({c["id"] for c in cases}) == len(cases)
    yes = sum(1 for c in cases if c["expect"]["needs_reply"])
    assert 0.35 <= yes / len(cases) <= 0.65


def test_debt_every_case_message_is_ambiguous_in_production():
    from services import reply_debts

    bad = [c["id"] for c in dv.load_synthetic() if not reply_debts.is_ambiguous(c["message"])]
    assert bad == []


def test_debt_prompt_uses_production_builder_with_marked_last_message():
    from services import debt_judge

    case = dv.load_synthetic()[0]
    prompt = dv.build_prompt(case)
    assert debt_judge.FINAL_MARK in prompt
    assert case["message"] in prompt and "Usuário:" in prompt


def test_debt_score_with_valid_wrong_and_failed_answers():
    case = {"id": "x", "kind": "synthetic", "expect": {"needs_reply": True}}
    assert dv.score(case, {"needs_reply": True, "reason": "r"})["ok"]
    wrong = dv.score(case, {"needs_reply": False, "reason": "r"})
    assert not wrong["ok"] and wrong["fn"]
    assert not dv.score(case, None)["valid"]
    assert not dv.score(case, {"needs_reply": "yes"})["ok"]


def _debt_oracle(monkeypatch, correct: bool):
    by_prompt = {dv.build_prompt(c): c["expect"]["needs_reply"] for c in dv.load_synthetic()}

    def fake(task, prompt, schema, *, provider=None, models=None):
        assert task == "DEBT" and provider == "openrouter"
        return {"needs_reply": by_prompt[prompt] == correct, "reason": "fake"}

    monkeypatch.setattr(llm_structured, "run_structured", fake)


def test_debt_threshold_gate_exit_codes(monkeypatch):
    _debt_oracle(monkeypatch, correct=True)
    out: list[str] = []
    assert dv.run("synthetic", "openrouter", ["m1"], out=out.append) == 0
    assert "accuracy=100%" in out[0]
    _debt_oracle(monkeypatch, correct=False)
    out = []
    assert dv.run("synthetic", "openrouter", ["m1"], out=out.append) == 1
    assert any("GATE FAILED" in line for line in out) and any("FAIL " in line for line in out)
    assert dv.run("synthetic", "openrouter", ["m1"], min_accuracy=0.0, out=lambda _s: None) == 0


def test_debt_ambiguous_cases_are_not_scored(tmp_path, monkeypatch):
    path = tmp_path / "c.yaml"
    path.write_text(
        '- {id: a, context: [], message: "ok entao", expect: {needs_reply: false}}\n'
        '- {id: b, context: [], message: "talvez", expect: {needs_reply: true}, ambiguous: true}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        llm_structured, "run_structured", lambda *a, **k: {"needs_reply": False, "reason": ""}
    )
    out: list[str] = []
    assert dv.run("synthetic", "openrouter", ["m"], synthetic_path=path, out=out.append) == 0
    assert "n=1 (excluded 1)" in out[0]


def test_debt_main_flags(monkeypatch):
    _debt_oracle(monkeypatch, correct=False)
    assert dv.main(["debt", "--model", "a", "--min-accuracy", "0.0"]) == 0
    assert dv.main(["debt", "--model", "a", "--min-accuracy", "0.99"]) == 1
