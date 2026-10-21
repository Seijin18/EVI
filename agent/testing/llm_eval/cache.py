"""Answer cache for ``evi-test llm-eval`` (SCN-SIM-12).

Re-running an evaluation with the same prompt, schema and model must not pay again. While
``cached_structured()`` is active, ``services.llm_structured.run_structured`` is wrapped: the
key is sha256(task, provider, models, the task's ``EVI_LLM_TASK_<T>_*`` env, prompt, schema)
and the value a list of samples. The i-th identical call of a run uses sample i when it
exists and calls the provider otherwise, so ``--repeat N`` keeps N distinct samples and the
next run reuses them. Failed calls (``None``) are never cached. The file lives under
``data/`` (gitignored): prompts may contain real cases. ``--no-cache`` or
``EVI_LLM_EVAL_CACHE=0`` bypasses it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = REPO_ROOT / "data" / "eval" / "cache.jsonl"
NO_CACHE_FLAG = "--no-cache"


def cache_enabled(extra: list[str]) -> bool:
    return NO_CACHE_FLAG not in extra and os.getenv("EVI_LLM_EVAL_CACHE", "1").strip() != "0"


def strip_flag(extra: list[str]) -> list[str]:
    return [a for a in extra if a != NO_CACHE_FLAG]


def cache_key(task: str, prompt: str, schema: dict, provider: str | None, models: list[str] | None) -> str:
    t = (task or "").strip().upper()
    env = {k: v for k, v in sorted(os.environ.items()) if k.startswith(f"EVI_LLM_TASK_{t}_")}
    blob = json.dumps(
        {"task": t, "provider": provider, "models": list(models or []), "env": env, "prompt": prompt, "schema": schema},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class EvalCache:
    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        self.samples: dict[str, list[dict]] = {}
        self.used: Counter = Counter()
        self.hits = 0
        self.misses = 0
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row.get("out"), dict):
                    self.samples.setdefault(row["key"], []).append(row["out"])

    def call(self, real, task: str, prompt: str, schema: dict, *, provider=None, models=None):  # noqa: ANN001
        key = cache_key(task, prompt, schema, provider, models)
        i = self.used[key]
        self.used[key] += 1
        cached = self.samples.get(key) or []
        if i < len(cached):
            self.hits += 1
            return copy.deepcopy(cached[i])
        self.misses += 1
        out = real(task, prompt, schema, provider=provider, models=models)
        if isinstance(out, dict):
            self.samples.setdefault(key, []).append(out)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "task": (task or "").upper(), "out": out}, ensure_ascii=False) + "\n")
        return out

    def summary(self) -> str:
        return f"llm-eval cache: {self.hits} reused, {self.misses} provider calls ({self.path})"


@contextmanager
def cached_structured(enabled: bool = True, path: Path = CACHE_PATH):
    """Wrap ``llm_structured.run_structured`` for the duration of an evaluation run."""
    if not enabled:
        yield None
        return
    from services import llm_structured

    cache = EvalCache(path)
    real = llm_structured.run_structured

    def wrapper(task, prompt, schema, *, provider=None, models=None):  # noqa: ANN001
        return cache.call(real, task, prompt, schema, provider=provider, models=models)

    llm_structured.run_structured = wrapper
    try:
        yield cache
    finally:
        llm_structured.run_structured = real
        print(cache.summary())
