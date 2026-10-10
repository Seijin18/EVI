"""In-container LLM call counter for evi-sim (imported by the sim image entrypoint only).

Registers a global LangChain callback (``register_configure_hook``) so EVERY chat-model
invocation in the agent process (ReAct loop, background extractors, summaries) appends
one line to ``/tmp/evi-sim-llm-calls``. The runner reads the line count before/after a
scenario attempt (delta), through ``docker compose exec``. This counts calls the agent
really makes, regardless of provider or code path, and needs no change to production
code: ``Dockerfile.sim`` starts uvicorn via ``python -c "import testing.sim.llm_counter"``.
"""

from __future__ import annotations

import time
from contextvars import ContextVar

COUNT_FILE = "/tmp/evi-sim-llm-calls"


def _record(kind: str) -> None:
    try:
        with open(COUNT_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f} {kind}\n")
    except OSError:
        pass


def install() -> None:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.tracers.context import register_configure_hook

    class _Counter(BaseCallbackHandler):
        def on_chat_model_start(self, serialized, messages, **kwargs):  # noqa: ANN001
            _record("chat")

        def on_llm_start(self, serialized, prompts, **kwargs):  # noqa: ANN001
            _record("llm")

    var: ContextVar = ContextVar("evi_sim_llm_counter", default=_Counter())
    register_configure_hook(var, inheritable=True)


install()
