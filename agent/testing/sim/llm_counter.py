"""In-container LLM call counter for evi-sim (imported by the sim image entrypoint only).

Registers a global LangChain callback (``register_configure_hook``) so EVERY chat-model
invocation in the agent process (ReAct loop, background extractors, summaries) appends
one line to ``/tmp/evi-sim-llm-calls``. The runner reads the line count before/after a
scenario attempt (delta), through ``docker compose exec``. This counts calls the agent
really makes, regardless of provider or code path, and needs no change to production
code: ``Dockerfile.sim`` starts uvicorn via ``python -c "import testing.sim.llm_counter"``.
"""

from __future__ import annotations

import json
import time
from contextvars import ContextVar

COUNT_FILE = "/tmp/evi-sim-llm-calls"
# One JSON line {"in","out","reasoning"} per finished REAL model call (the runner sums deltas).
USAGE_FILE = "/tmp/evi-sim-llm-usage"
_WRAPPER = "SimCassetteChatModel"  # cassette wrapper: its inner model fires its own callbacks


def _record(kind: str) -> None:
    try:
        with open(COUNT_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f} {kind}\n")
    except OSError:
        pass


def _record_usage(tin: int, tout: int, reasoning: int) -> None:
    try:
        with open(USAGE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"in": tin, "out": tout, "reasoning": reasoning}) + "\n")
    except OSError:
        pass


def install() -> None:
    from llm_usage import extract_usage
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.tracers.context import register_configure_hook

    class _Counter(BaseCallbackHandler):
        def __init__(self) -> None:
            self._wrappers: set = set()

        def on_chat_model_start(self, serialized, messages, *, run_id=None, **kwargs):  # noqa: ANN001
            ident = (serialized or {}).get("id") or []
            if kwargs.get("name") == _WRAPPER or (ident and ident[-1] == _WRAPPER):
                self._wrappers.add(run_id)  # record mode: count tokens on the inner model only
            _record("chat")

        def on_llm_end(self, response, *, run_id=None, **kwargs):  # noqa: ANN001
            if run_id in self._wrappers:
                self._wrappers.discard(run_id)
                return  # replay: nothing was billed; record: the inner call reports it
            _record_usage(*extract_usage(response))

        def on_llm_start(self, serialized, prompts, **kwargs):  # noqa: ANN001
            _record("llm")

    var: ContextVar = ContextVar("evi_sim_llm_counter", default=_Counter())
    register_configure_hook(var, inheritable=True)


install()
