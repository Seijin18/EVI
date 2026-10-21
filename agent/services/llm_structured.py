"""Structured (JSON-schema) LLM calls per task, with per-task provider/model.

    run_structured(task, prompt, schema) -> dict | None

Provider and model come from ``EVI_LLM_TASK_<TASK>_PROVIDER`` / ``_MODEL`` (a
comma-separated model list is a fallback chain within the same provider). Any failure
returns None; there is no automatic cross-provider fallback (opt-in only via
``EVI_LLM_TASK_<TASK>_FALLBACK``). OpenRouter calls always force ZDR and no data
collection, and are bounded by a daily USD cap (``EVI_LLM_TASK_DAILY_USD``).
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import threading
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger("evi.llm_structured")

# Known limits: concurrent calls can overshoot the daily cap by up to N x one call's cost
# (the check precedes the call); without DATABASE_URL the counter is per-process only.

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROVIDERS = ("openrouter", "ollama", "gemini")

# Per-task defaults; other changes add their task here.
DEFAULTS: dict[str, dict[str, str]] = {
    "PROMISE": {
        "provider": "openrouter",
        "model": "google/gemma-4-31b-it,qwen/qwen3.8-27b",
    },
    "TASK": {
        "provider": "openrouter",
        "model": "google/gemma-4-31b-it,qwen/qwen3.8-27b",
    },
    "DEBT": {
        "provider": "openrouter",
        "model": "google/gemma-4-31b-it,qwen/qwen3.8-27b",
    },
    "CONTACT_KNOWLEDGE": {
        "provider": "openrouter",
        "model": "google/gemma-4-26b-a4b-it,qwen/qwen3.8-27b",
    },
    "CONTACT_NAME_HINT": {
        "provider": "openrouter",
        "model": "google/gemma-4-26b-a4b-it,qwen/qwen3.8-27b",
    },
}


# ---------------------------------------------------------------- schema helpers


def strictify(schema: dict) -> dict:
    """Deep copy with every object node closed: additionalProperties False, all keys required."""
    out = copy.deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                props = node.get("properties") or {}
                node["additionalProperties"] = False
                node["required"] = list(props.keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)
    return out


_GEMINI_KEEP = {"type", "properties", "items", "enum", "description", "nullable", "required", "propertyOrdering"}


def _to_gemini_schema(schema: Any) -> Any:
    """JSON schema -> Gemini's OpenAPI subset (drops unsupported keys, adds propertyOrdering)."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k not in _GEMINI_KEEP:
            continue
        if k == "properties" and isinstance(v, dict):
            out[k] = {name: _to_gemini_schema(sub) for name, sub in v.items()}
            out["propertyOrdering"] = list(v.keys())
        elif k == "items":
            out[k] = _to_gemini_schema(v)
        elif k == "type" and isinstance(v, list):
            non_null = [t for t in v if t != "null"]
            out[k] = non_null[0] if non_null else "string"
            if "null" in v:
                out["nullable"] = True
        elif k == "propertyOrdering":
            continue
        else:
            out[k] = v
    return out


_TYPES = {
    "string": str,
    "boolean": bool,
    "object": dict,
    "array": list,
    "null": type(None),
}


def _type_ok(value: Any, typ: str) -> bool:
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py = _TYPES.get(typ)
    return True if py is None else isinstance(value, py)


def _valid(value: Any, schema: dict) -> bool:
    typ = schema.get("type")
    if typ is not None:
        types = typ if isinstance(typ, list) else [typ]
        if not any(_type_ok(value, t) for t in types):
            return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                return False
        for key, sub in (schema.get("properties") or {}).items():
            if key in value and not _valid(value[key], sub):
                return False
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        return all(_valid(v, schema["items"]) for v in value)
    return True


# ---------------------------------------------------------------- config


def _env(task: str, suffix: str) -> str:
    return os.getenv(f"EVI_LLM_TASK_{task}_{suffix}", "").strip()


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _timeout() -> float:
    return _float_env("EVI_LLM_TASK_TIMEOUT_SEC", 30.0)


def _resolve(task: str) -> tuple[str, list[str]]:
    d = DEFAULTS.get(task, {})
    provider = (_env(task, "PROVIDER") or d.get("provider") or "ollama").lower()
    raw = _env(task, "MODEL") or d.get("model") or ""
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return provider, models


def _default_model(provider: str) -> list[str]:
    if provider == "ollama":
        return [os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M")]
    if provider == "gemini":
        return [os.getenv("GEMINI_MODEL", "gemini-2.0-flash")]
    return []


# ---------------------------------------------------------------- spend cap

_mem_lock = threading.Lock()
_mem_usage: dict[tuple[date, str], float] = {}
_table_ready = False


def _today() -> date:
    try:
        tz = ZoneInfo(os.getenv("EVI_TIMEZONE", "America/Sao_Paulo"))
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")
    return datetime.now(tz).date()


def _use_db() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


def _ensure_table(conn, cur) -> None:
    global _table_ready
    if _table_ready:
        return
    _table_ready = False
    cur.execute(
        "CREATE TABLE IF NOT EXISTS llm_task_usage ("
        " day date NOT NULL, task text NOT NULL,"
        " calls integer NOT NULL DEFAULT 0,"
        " cost_usd numeric NOT NULL DEFAULT 0,"
        " PRIMARY KEY (day, task))"
    )
    conn.commit()
    _table_ready = True


def _spent_today() -> float:
    """Today's spend. With a DB configured, a failed read means "unknown": fail closed (inf)."""
    day = _today()
    with _mem_lock:
        mem = sum(c for (d, _t), c in _mem_usage.items() if d == day)
    if not _use_db():
        return mem
    try:
        import db

        with db._conn() as conn, conn.cursor() as cur:
            _ensure_table(conn, cur)
            cur.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_task_usage WHERE day = %s", (day,))
            total = float(cur.fetchone()[0])
            conn.commit()
    except Exception as exc:
        logger.warning("llm_structured: usage read failed (%s); treating cap as reached", type(exc).__name__)
        return float("inf")
    return total + mem  # mem = costs whose DB write failed earlier


def _record_usage(task: str, cost: float) -> None:
    day = _today()
    if _use_db():
        try:
            import db

            with db._conn() as conn, conn.cursor() as cur:
                _ensure_table(conn, cur)
                cur.execute(
                    "INSERT INTO llm_task_usage (day, task, calls, cost_usd) VALUES (%s, %s, 1, %s) "
                    "ON CONFLICT (day, task) DO UPDATE SET calls = llm_task_usage.calls + 1, "
                    "cost_usd = llm_task_usage.cost_usd + EXCLUDED.cost_usd",
                    (day, task, cost),
                )
                conn.commit()
            return
        except Exception as exc:
            logger.warning("llm_structured: usage write failed (%s); using in-memory counter", type(exc).__name__)
    with _mem_lock:
        _mem_usage[(day, task)] = _mem_usage.get((day, task), 0.0) + cost


def _clean_cost(raw: Any) -> float:
    try:
        c = float(raw or 0)
    except (TypeError, ValueError):
        return 0.0
    return c if math.isfinite(c) and c >= 0 else 0.0


def _cap_reached() -> bool:
    return _spent_today() >= _float_env("EVI_LLM_TASK_DAILY_USD", 0.10)


# ---------------------------------------------------------------- providers


def _parse(text: Any) -> dict | None:
    if not isinstance(text, str):
        return None
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _call_openrouter(task: str, prompt: str, schema: dict, models: list[str]) -> str | None:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key or not models:
        return None
    body: dict[str, Any] = {
        "model": models[0],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "provider": {"zdr": True, "data_collection": "deny", "require_parameters": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "out", "strict": True, "schema": strictify(schema)},
        },
        "usage": {"include": True},
    }
    if len(models) > 1:
        body["models"] = models
    resp = httpx.post(
        OPENROUTER_URL,
        json=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=_timeout(),
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        _record_usage(task, 0.0)
        return None
    _record_usage(task, _clean_cost((data.get("usage") or {}).get("cost")))
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content")


def _call_ollama(task: str, prompt: str, schema: dict, models: list[str]) -> str | None:
    base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
    body: dict[str, Any] = {
        "model": models[0],
        "messages": [{"role": "user", "content": prompt}],
        "format": schema,
        "options": {"temperature": 0},
        "stream": False,
    }
    think = _env(task, "THINK").lower()
    if think:
        body["think"] = think in ("1", "true", "yes", "on")
    resp = httpx.post(f"{base}/api/chat", json=body, timeout=_timeout())
    resp.raise_for_status()
    return (resp.json().get("message") or {}).get("content")


def _call_gemini(task: str, prompt: str, schema: dict, models: list[str]) -> str | None:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": _to_gemini_schema(schema),
        },
    }
    resp = httpx.post(
        GEMINI_URL.format(model=models[0]),
        json=body,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        timeout=_timeout(),
    )
    resp.raise_for_status()
    parts = (((resp.json().get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict)) or None


_CALLERS = {"openrouter": _call_openrouter, "ollama": _call_ollama, "gemini": _call_gemini}


def _attempt(
    task: str, provider: str, models: list[str], prompt: str, schema: dict
) -> tuple[dict | None, bool]:
    """(result, capped). ``capped`` is True when the spend cap blocked the call."""
    caller = _CALLERS.get(provider)
    if caller is None:
        logger.warning("llm_structured: task=%s unknown provider=%s", task, provider)
        return None, False
    models = models or _default_model(provider)
    if not models and provider != "gemini":
        logger.warning("llm_structured: task=%s provider=%s no model configured", task, provider)
        return None, False
    try:
        if provider == "openrouter" and _cap_reached():
            logger.warning("llm_structured: task=%s provider=openrouter daily cap reached", task)
            return None, True
        text = caller(task, prompt, schema, models)
    except Exception as exc:
        logger.warning("llm_structured: task=%s provider=%s failed: %s", task, provider, type(exc).__name__)
        return None, False
    if text is None:
        logger.warning("llm_structured: task=%s provider=%s empty response or missing key", task, provider)
        return None, False
    data = _parse(text)
    if data is None or not _valid(data, schema):
        logger.warning("llm_structured: task=%s provider=%s invalid JSON/schema", task, provider)
        return None, False
    return data, False


def _sim_cassette_mode() -> str | None:
    """"record" / "replay" / "fill" under evi-sim (EVI_SIM=1 and EVI_LLM_PROVIDER=sim-record|sim-replay|sim-fill)."""
    if os.getenv("EVI_SIM", "").strip() != "1":
        return None
    return {"sim-record": "record", "sim-replay": "replay", "sim-fill": "fill"}.get(os.getenv("EVI_LLM_PROVIDER", "").strip().lower())


def run_structured(
    task: str,
    prompt: str,
    schema: dict,
    *,
    provider: str | None = None,
    models: list[str] | None = None,
) -> dict | None:
    """Run ``prompt`` and return a dict matching ``schema``, or None on any failure.

    ``provider``/``models`` override the env configuration (used by the evaluator to
    compare models); with an override the opt-in fallback is not tried.
    """
    t = (task or "").strip().upper()
    sim = _sim_cassette_mode()
    if sim:  # evi-sim only: deterministic record/replay of structured calls
        from testing.sim.cassette import structured_call

        return structured_call(
            sim, t, prompt, schema, lambda: _run_structured(t, prompt, schema, provider=provider, models=models)
        )
    return _run_structured(t, prompt, schema, provider=provider, models=models)


def _run_structured(
    t: str, prompt: str, schema: dict, *, provider: str | None = None, models: list[str] | None = None
) -> dict | None:
    if provider is not None:
        return _attempt(t, provider.lower(), list(models or []), prompt, schema)[0]
    prov, mods = _resolve(t)
    if models:
        mods = list(models)
    result, capped = _attempt(t, prov, mods, prompt, schema)
    if result is not None or capped:
        return result
    fb = _env(t, "FALLBACK").lower()
    if fb in PROVIDERS and fb != prov:
        fb_models = [m.strip() for m in _env(t, "FALLBACK_MODEL").split(",") if m.strip()]
        return _attempt(t, fb, fb_models, prompt, schema)[0]
    return None
