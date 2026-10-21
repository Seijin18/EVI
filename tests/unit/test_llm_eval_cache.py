"""llm-eval answer cache (SCN-SIM-12): reuse unchanged answers, N samples for --repeat N, bypass."""
from __future__ import annotations

from services import llm_structured
from testing.llm_eval import cache

SCHEMA = {"type": "object"}


def _fake_provider(monkeypatch):
    calls = []

    def real(task, prompt, schema, *, provider=None, models=None):  # noqa: ANN001
        calls.append((task, prompt, provider, tuple(models or ())))
        return {"n": len(calls)}

    monkeypatch.setattr(llm_structured, "run_structured", real)
    return calls


def _run(path, prompts, provider="openrouter", models=("m1",)):
    with cache.cached_structured(True, path):
        return [llm_structured.run_structured("DEBT", p, SCHEMA, provider=provider, models=list(models)) for p in prompts]


def test_second_run_is_free(tmp_path, monkeypatch):
    calls = _fake_provider(monkeypatch)
    path = tmp_path / "cache.jsonl"
    first = _run(path, ["a", "b"])
    again = _run(path, ["a", "b"])
    assert first == again == [{"n": 1}, {"n": 2}]
    assert len(calls) == 2


def test_repeat_keeps_distinct_samples(tmp_path, monkeypatch):
    calls = _fake_provider(monkeypatch)
    path = tmp_path / "cache.jsonl"
    assert _run(path, ["a", "a", "a"]) == [{"n": 1}, {"n": 2}, {"n": 3}]
    assert _run(path, ["a", "a", "a"]) == [{"n": 1}, {"n": 2}, {"n": 3}]
    assert _run(path, ["a"] * 4)[-1] == {"n": 4}  # a 4th sample is new: one real call
    assert len(calls) == 4


def test_changed_prompt_model_or_task_env_is_a_miss(tmp_path, monkeypatch):
    calls = _fake_provider(monkeypatch)
    path = tmp_path / "cache.jsonl"
    _run(path, ["a"])
    _run(path, ["a mudou"])
    _run(path, ["a"], models=("m2",))
    monkeypatch.setenv("EVI_LLM_TASK_DEBT_MODEL", "outro")
    _run(path, ["a"])
    assert len(calls) == 4


def test_failures_are_not_cached(tmp_path, monkeypatch):
    calls = []

    def flaky(task, prompt, schema, *, provider=None, models=None):  # noqa: ANN001
        calls.append(1)
        return None if len(calls) == 1 else {"ok": True}

    monkeypatch.setattr(llm_structured, "run_structured", flaky)
    path = tmp_path / "cache.jsonl"
    assert _run(path, ["a"]) == [None]
    assert _run(path, ["a"]) == [{"ok": True}]
    assert len(calls) == 2


def test_bypass_flag_and_env(monkeypatch):
    assert cache.cache_enabled(["debt"])
    assert not cache.cache_enabled(["debt", "--no-cache"])
    assert cache.strip_flag(["debt", "--no-cache", "--repeat", "3"]) == ["debt", "--repeat", "3"]
    monkeypatch.setenv("EVI_LLM_EVAL_CACHE", "0")
    assert not cache.cache_enabled(["debt"])


def test_wrapper_is_removed_after_the_run(tmp_path, monkeypatch):
    _fake_provider(monkeypatch)
    original = llm_structured.run_structured
    _run(tmp_path / "cache.jsonl", ["a"])
    assert llm_structured.run_structured is original
