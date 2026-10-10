"""Per-turn collector feeding `turn_log` (evi-usage-validation).

Tools hand LangChain a plain `str` (decision #34), so the structured outcome
never reaches the graph result. `parse_windmill_result` therefore reports
`{tool, ok, reason}` into a per-turn collector held in a ContextVar, opened by
the /chat handler. The same object is a LangChain callback handler: it counts
chat-model calls and times each tool call, so tools without Windmill (notes,
contacts, RAG) still show up — with `ok: None` (unknown, not success).

The collector is a mutable object on purpose: LangGraph may run sync tools in a
thread pool with a *copied* context, and a copy still points at the same object.
Recording is best-effort — a logging failure never breaks a turn.
"""

from __future__ import annotations

import threading
import time
from contextvars import ContextVar
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from services.soft_fail import soft_fail

TEST_SESSION_PREFIXES = ("evi-test", "test-", "health-check", "tg-digest-verify")

REASON_EXCEPTION = "exception"


def is_test_session(session_id: str | None) -> bool:
    return bool(session_id) and str(session_id).startswith(TEST_SESSION_PREFIXES)


_seq_lock = threading.Lock()
_last_seq = 0


def _next_turn_seq() -> int:
    """Strictly increasing turn id, comparable across turns (and restarts):
    wall-clock nanoseconds, bumped by 1 when two turns start in the same tick."""
    global _last_seq
    with _seq_lock:
        _last_seq = max(time.time_ns(), _last_seq + 1)
        return _last_seq


class TurnCollector(BaseCallbackHandler):
    """Collects tool outcomes, tool timings and LLM call count for one turn."""

    def __init__(
        self,
        channel: str | None = None,
        is_test: bool = False,
        session_id: str | None = None,
        input_kind: str = "text",
        user_text: str = "",
    ) -> None:
        self.channel = channel
        self.user_text = user_text or ""
        self.turn_seq = _next_turn_seq()
        self.input_kind = input_kind or "text"
        self.session_id = session_id
        self.is_test = bool(is_test)
        self._lock = threading.Lock()
        self._windmill: list[dict[str, Any]] = []
        self._calls: list[dict[str, Any]] = []
        self._running: dict[Any, tuple[int, float]] = {}
        from services.slow_ack import SlowAck

        self._slow_ack = SlowAck(self)
        self.llm_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    # -- fed by parse_windmill_result -------------------------------------
    def record_outcome(self, tool: str, ok: bool, reason: str = "") -> None:
        with self._lock:
            self._windmill.append({"name": tool, "ok": bool(ok), "reason": reason or None})

    # -- LangChain callbacks ----------------------------------------------
    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        with self._lock:
            self.llm_calls += 1

    def on_llm_start(self, serialized, prompts, **kwargs) -> None:
        # Chat models fire on_chat_model_start only; this covers plain LLMs.
        with self._lock:
            self.llm_calls += 1

    def on_llm_end(self, response, **kwargs) -> None:
        from llm_usage import extract_usage

        tin, tout, _ = extract_usage(response)
        with self._lock:
            self.tokens_in += tin
            self.tokens_out += tout

    def on_tool_start(self, serialized, input_str, *, run_id=None, **kwargs) -> None:
        name = kwargs.get("name") or (serialized or {}).get("name") or "?"
        with self._lock:
            self._calls.append({"name": name, "ok": None, "reason": None, "ms": None, "_err": False})
            self._running[run_id] = (len(self._calls) - 1, time.monotonic())
        self._slow_ack.tool_started(run_id, name)

    def _finish_call(self, run_id, *, error: bool) -> None:
        self._slow_ack.tool_ended(run_id)
        with self._lock:
            started = self._running.pop(run_id, None)
            if started is None:
                return
            idx, t0 = started
            self._calls[idx]["ms"] = int((time.monotonic() - t0) * 1000)
            self._calls[idx]["_err"] = error

    def on_tool_end(self, output, *, run_id=None, **kwargs) -> None:
        self._finish_call(run_id, error=False)

    def on_tool_error(self, error, *, run_id=None, **kwargs) -> None:
        self._finish_call(run_id, error=True)

    # -- result -----------------------------------------------------------
    def close(self) -> None:
        """End of turn: drop any pending slow-tool ack timer."""
        self._slow_ack.cancel()

    def tools(self) -> list[dict[str, Any]]:
        """Tool calls in order, each merged with its Windmill outcome by name."""
        with self._lock:
            pending = list(self._windmill)
            out: list[dict[str, Any]] = []
            for call in self._calls:
                entry = {"name": call["name"], "ok": None, "reason": None, "ms": call["ms"]}
                for i, w in enumerate(pending):
                    if w["name"] == call["name"]:
                        entry["ok"], entry["reason"] = w["ok"], w["reason"]
                        del pending[i]
                        break
                if call["_err"]:
                    entry["ok"], entry["reason"] = False, REASON_EXCEPTION
                out.append(entry)
            # Windmill outcomes from code that ran outside a recorded tool call.
            for w in pending:
                out.append({"name": w["name"], "ok": w["ok"], "reason": w["reason"], "ms": None})
            return out


_current: ContextVar[TurnCollector | None] = ContextVar("evi_turn_collector", default=None)


def start_turn(
    channel: str | None = None,
    session_id: str | None = None,
    is_test: bool = False,
    input_kind: str = "text",
    user_text: str = "",
) -> tuple[TurnCollector, Any]:
    collector = TurnCollector(
        channel,
        bool(is_test) or is_test_session(session_id),
        session_id,
        input_kind,
        user_text,
    )
    return collector, _current.set(collector)


def current_channel() -> str | None:
    """Channel of the turn in progress (None outside a /chat turn)."""
    collector = _current.get()
    return collector.channel if collector is not None else None


def current_session_id() -> str | None:
    """Session id of the turn in progress (None outside a /chat turn)."""
    collector = _current.get()
    return getattr(collector, "session_id", None) if collector is not None else None


def current_user_text() -> str:
    """The user's message of the turn in progress, as set by the handler (never by
    the model). Empty outside a /chat turn."""
    collector = _current.get()
    return str(getattr(collector, "user_text", "") or "") if collector is not None else ""


def current_turn_seq() -> int | None:
    """Strictly increasing id of the turn in progress (None outside a /chat turn)."""
    collector = _current.get()
    return getattr(collector, "turn_seq", None) if collector is not None else None


def current_is_test() -> bool:
    """True when the turn in progress is a test turn (header or test session id)."""
    collector = _current.get()
    return bool(collector.is_test) if collector is not None else False


def end_turn(token: Any) -> None:
    collector = _current.get()
    if collector is not None:
        try:
            collector.close()
        except Exception as exc:
            soft_fail("turn_log.end_turn.close", exc)
    try:
        _current.reset(token)
    except ValueError:  # token from another context; leave the var as is
        _current.set(None)


def record_tool_outcome(tool: str, ok: bool, reason: str = "") -> None:
    """Called by parse_windmill_result; a no-op outside a /chat turn."""
    collector = _current.get()
    if collector is not None and tool:
        collector.record_outcome(tool, ok, reason)


def _briefing_enabled() -> bool:
    from services.heartbeat import _briefing_enabled as enabled

    return enabled()


def record_turn(
    collector: TurnCollector | None,
    *,
    session_id: str,
    channel: str,
    user_text: str,
    reply_text: str | None,
    latency_ms: int,
    error: str | None = None,
    is_test: bool = False,
) -> None:
    """Persist one turn to `turn_log`. Never raises; no-op without DATABASE_URL.

    `is_test` forces the flag (X-Evi-Test header); test-prefixed session ids are
    flagged regardless. Test turns never feed the Prometheus turn counter."""
    import os

    test = bool(is_test) or is_test_session(session_id)
    tools = collector.tools() if collector else []
    if not test:
        try:
            from services import metrics

            if error:
                outcome = "error"
            elif any(t.get("ok") is False for t in tools):
                outcome = "tool_failed"
            else:
                outcome = "ok"
            metrics.record_turn(channel, outcome)
        except Exception as exc:
            soft_fail("turn_log.record_turn.metrics", exc)
    if (
        not test
        and channel == "telegram"
        and os.getenv("DATABASE_URL")
        and _briefing_enabled()
    ):
        try:
            from services import briefing

            briefing.note_user_reply(user_text=user_text)
        except Exception as exc:
            soft_fail("turn_log.record_turn.briefing_reply", exc)
    if not os.getenv("DATABASE_URL"):
        return
    try:
        from db import insert_turn

        insert_turn(
            session_id=session_id,
            channel=channel,
            user_text=user_text,
            reply_text=reply_text,
            tools=tools,
            latency_ms=latency_ms,
            llm_calls=collector.llm_calls if collector else None,
            tokens_in=(collector.tokens_in or None) if collector else None,
            tokens_out=(collector.tokens_out or None) if collector else None,
            error=error,
            is_test=test,
            input_kind=(collector.input_kind if collector else "text"),
        )
    except Exception as exc:
        soft_fail("turn_log.record_turn", exc)
