"""llm_structured: SCN-LLM-TASK-01..04 (HTTP mocked, no network)."""

import json

import httpx
import pytest

from services import llm_structured as ls

SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "decision": {"type": "boolean"},
        "inner": {"type": "object", "properties": {"n": {"type": "integer"}}},
    },
    "required": ["reasoning", "decision"],
}
GOOD = {"reasoning": "r", "decision": True}


class FakeHttp:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        out = self.handler(url, json)
        if isinstance(out, Exception):
            raise out
        req = httpx.Request("POST", url)
        return httpx.Response(200, content=__import__("json").dumps(out).encode(), request=req)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("EVI_LLM_TASK_"):
            monkeypatch.delenv(k)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k-or")
    monkeypatch.setenv("GEMINI_API_KEY", "k-gem")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")
    monkeypatch.setattr(ls, "_mem_usage", {})


def _install(monkeypatch, handler):
    fake = FakeHttp(handler)
    monkeypatch.setattr(ls.httpx, "post", fake.post)
    return fake


def _or_ok(cost=0.01, content=None):
    return {
        "choices": [{"message": {"content": json.dumps(content or GOOD)}}],
        "usage": {"cost": cost},
    }


def test_scn01_gemini_with_response_schema_and_other_task_keeps_own_provider(monkeypatch):
    monkeypatch.setenv("EVI_LLM_TASK_PROMISE_PROVIDER", "gemini")
    monkeypatch.setenv("EVI_LLM_TASK_PROMISE_MODEL", "gemini-x")

    def h(url, body):
        if "generativelanguage" in url:
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD)}]}}]}
        return {"message": {"content": json.dumps(GOOD)}}

    fake = _install(monkeypatch, h)
    assert ls.run_structured("promise", "p", SCHEMA) == GOOD
    url = fake.calls[0]["url"]
    assert "generativelanguage.googleapis.com" in url and "gemini-x" in url
    cfg = fake.calls[0]["json"]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert cfg["responseSchema"]["propertyOrdering"] == ["reasoning", "decision", "inner"]
    assert "additionalProperties" not in json.dumps(cfg["responseSchema"])

    assert ls.run_structured("knowledge", "p", SCHEMA) == GOOD
    assert fake.calls[1]["url"] == "http://ollama.test:11434/api/chat"


def test_scn02_ollama_down_no_fallback_makes_no_other_request(monkeypatch):
    monkeypatch.setenv("EVI_LLM_TASK_PROMISE_PROVIDER", "ollama")
    fake = _install(monkeypatch, lambda u, b: httpx.ConnectError("down"))
    assert ls.run_structured("promise", "p", SCHEMA) is None
    assert [c["url"] for c in fake.calls] == ["http://ollama.test:11434/api/chat"]


def test_scn03_openrouter_body_is_zdr_strict(monkeypatch):
    fake = _install(monkeypatch, lambda u, b: _or_ok())
    assert ls.run_structured("promise", "p", SCHEMA) == GOOD
    call = fake.calls[0]
    body = call["json"]
    assert call["url"] == ls.OPENROUTER_URL
    assert body["provider"] == {"zdr": True, "data_collection": "deny", "require_parameters": True}
    assert body["temperature"] == 0 and body["usage"] == {"include": True}
    rf = body["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    sch = rf["json_schema"]["schema"]
    assert sch["additionalProperties"] is False
    assert sch["required"] == ["reasoning", "decision", "inner"]
    assert sch["properties"]["inner"]["additionalProperties"] is False
    assert body["model"] == "google/gemma-4-31b-it"
    assert body["models"] == ["google/gemma-4-31b-it", "qwen/qwen3.8-27b"]
    assert "additionalProperties" not in SCHEMA  # strictify did not mutate input


def test_scn04_cap_reached_no_request(monkeypatch):
    monkeypatch.setenv("EVI_LLM_TASK_DAILY_USD", "0.10")
    ls._record_usage("OTHER", 0.10)
    fake = _install(monkeypatch, lambda u, b: _or_ok())
    assert ls.run_structured("promise", "p", SCHEMA) is None
    assert fake.calls == []


def test_cap_reached_does_not_trigger_fallback(monkeypatch):
    monkeypatch.setenv("EVI_LLM_TASK_PROMISE_FALLBACK", "ollama")
    ls._record_usage("PROMISE", 1.0)
    fake = _install(monkeypatch, lambda u, b: {"message": {"content": json.dumps(GOOD)}})
    assert ls.run_structured("promise", "p", SCHEMA) is None
    assert fake.calls == []


def test_cost_accumulates_until_cap(monkeypatch):
    monkeypatch.setenv("EVI_LLM_TASK_DAILY_USD", "0.05")
    fake = _install(monkeypatch, lambda u, b: _or_ok(cost=0.03))
    assert ls.run_structured("promise", "p", SCHEMA) == GOOD
    assert ls.run_structured("promise", "p", SCHEMA) == GOOD  # 0.03 < 0.05
    assert ls.run_structured("promise", "p", SCHEMA) is None  # 0.06 >= 0.05
    assert len(fake.calls) == 2


def test_no_openrouter_key_no_request(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    fake = _install(monkeypatch, lambda u, b: _or_ok())
    assert ls.run_structured("promise", "p", SCHEMA) is None
    assert fake.calls == []


@pytest.mark.parametrize(
    "content",
    ["not json", json.dumps({"reasoning": "x"}), json.dumps({"reasoning": "x", "decision": "yes"})],
)
def test_invalid_output_returns_none(monkeypatch, content):
    _install(monkeypatch, lambda u, b: {"choices": [{"message": {"content": content}}], "usage": {"cost": 0}})
    assert ls.run_structured("promise", "p", SCHEMA) is None


def test_fallback_only_when_opted_in(monkeypatch):
    monkeypatch.setenv("EVI_LLM_TASK_PROMISE_PROVIDER", "ollama")

    def h(url, body):
        if "ollama" in url:
            return httpx.ConnectError("down")
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD)}]}}]}

    fake = _install(monkeypatch, h)
    assert ls.run_structured("promise", "p", SCHEMA) is None
    assert len(fake.calls) == 1

    monkeypatch.setenv("EVI_LLM_TASK_PROMISE_FALLBACK", "gemini")
    assert ls.run_structured("promise", "p", SCHEMA) == GOOD
    assert "generativelanguage" in fake.calls[-1]["url"]


def test_ollama_request_shape_and_think(monkeypatch):
    monkeypatch.setenv("EVI_LLM_TASK_PROMISE_PROVIDER", "ollama")
    fake = _install(monkeypatch, lambda u, b: {"message": {"content": json.dumps(GOOD)}})
    ls.run_structured("promise", "p", SCHEMA)
    b = fake.calls[0]["json"]
    assert b["format"] == SCHEMA and b["stream"] is False and b["options"] == {"temperature": 0}
    assert "think" not in b
    monkeypatch.setenv("EVI_LLM_TASK_PROMISE_THINK", "true")
    ls.run_structured("promise", "p", SCHEMA)
    assert fake.calls[1]["json"]["think"] is True


def test_override_bypasses_env(monkeypatch):
    fake = _install(monkeypatch, lambda u, b: _or_ok())
    assert ls.run_structured("promise", "p", SCHEMA, provider="openrouter", models=["a/b"]) == GOOD
    assert fake.calls[0]["json"]["model"] == "a/b" and "models" not in fake.calls[0]["json"]


def test_db_read_failure_fails_closed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    import db

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "_conn", boom)
    fake = _install(monkeypatch, lambda u, b: _or_ok())
    assert ls.run_structured("promise", "p", SCHEMA) is None
    assert fake.calls == []


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), -5, "x"])
def test_bad_cost_does_not_lower_cap(monkeypatch, cost):
    ls._record_usage("PROMISE", 0.04)
    _install(monkeypatch, lambda u, b: {"choices": [{"message": {"content": json.dumps(GOOD)}}], "usage": {"cost": cost}})
    assert ls.run_structured("promise", "p", SCHEMA) == GOOD
    assert ls._spent_today() == pytest.approx(0.04)


def test_mem_fallback_added_to_db_total(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    import db

    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a):
            pass

        def fetchone(self):
            return (0.03,)

    class Conn(Cur):
        def cursor(self):
            return Cur()

        def commit(self):
            pass

    monkeypatch.setattr(db, "_conn", lambda: Conn())
    monkeypatch.setattr(ls, "_table_ready", True)
    ls._mem_usage[(ls._today(), "PROMISE")] = 0.02
    assert ls._spent_today() == pytest.approx(0.05)


def test_strictify_keeps_field_named_properties():
    s = ls.strictify({"type": "object", "properties": {"properties": {"type": "string"}}})
    assert s["properties"]["properties"] == {"type": "string"}
