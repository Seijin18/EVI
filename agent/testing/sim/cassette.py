"""LLM cassettes for evi-sim (task 4.1, SCN-SIM-09).

``EVI_LLM_PROVIDER=sim-record`` wraps the real Gemini chat model and appends one
``(key -> AIMessage)`` pair per call to a cassette; ``sim-replay`` serves those recorded
answers with no network. Both providers exist ONLY when ``EVI_SIM=1`` (``llm.build_llm``
imports this module lazily inside that branch; without it the names are "unknown provider").

Active cassette: the runner writes ``/tmp/evi-sim-cassettes/ctl`` ({"id","nonce"}) at the
start of every scenario attempt and copies ``<id>.jsonl`` into the same directory for
replay (record writes there; the runner copies it back out to ``tests/sim/cassettes``).
A new nonce resets consumption (``--repeat N`` replays the same cassette N times).

Key = sha256 of the NORMALIZED request (message roles/content/tool calls, bound tool
names + parameter schemas). Volatile parts are normalized so a cassette recorded on one
day replays on any other:
  * ISO dates become offsets from the container's "today" (``D+1``) -- the sim clock is
    relative to the real day, so relative dates are stable while absolute ones are not;
  * UUIDs become a placeholder everywhere; clock times, weekday names (en/pt) and pt-BR
    "12 de outubro" phrases become placeholders ONLY on the generated calendar header lines
    ("Today is ...", "Current time: ...", "- +N days ...") -- see _VOLATILE_LINE;
  * tool_call ids are ignored.
Recorded responses store ISO dates as the same offsets (``@@D+1@@``) and are shifted back to
the replay day, so a tool call recorded as "tomorrow" stays "tomorrow".

Same key several times in a scenario -> answers served in recorded order; asking more
times than recorded is stale too (an extra identical round-trip is a behavior change). Unknown key -> ``CassetteStale``
("cassette stale: regrave com --llm record"); it is also appended to ``stale.log`` so the
runner can surface it as the failure reason even if the agent swallows the exception.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

CASSETTE_DIR = Path(os.getenv("EVI_SIM_CASSETTE_DIR", "/tmp/evi-sim-cassettes"))
STALE_LOG = "stale.log"
STALE_MSG = "cassette stale: regrave com --llm record"

_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")  # also inside "2026-10-11T10:00:00"
_TOKEN = re.compile(r"@@D([+-]\d+)@@")
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\b")
_WEEKDAY = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|segunda(?:-feira)?|ter[cç]a(?:-feira)?|quarta(?:-feira)?|quinta(?:-feira)?"
    r"|sexta(?:-feira)?|s[aá]bado|domingo)\b",
    re.IGNORECASE,
)
_PT_DATE = re.compile(
    r"\b\d{1,2} de (?:janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro"
    r"|outubro|novembro|dezembro)(?: de \d{4})?\b",
    re.IGNORECASE,
)
# Lines of the generated calendar header (graph._calendar_block): the only place where the
# clock time / weekday / pt-BR date of "now" is injected. Time, weekday and pt-BR date
# placeholders apply ONLY to these lines, so a prompt edit that changes a time or weekday
# word elsewhere still makes the cassette stale. ISO dates (relative offsets) and UUIDs are
# normalized everywhere: dates because the sim clock follows the real day, UUIDs because
# they are random per run.
_VOLATILE_LINE = re.compile(r"^\s*(Today is\b|.*Current time:|- \+\d+ days\b)", re.IGNORECASE)
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)


# Deletion confirmation token (tools/email_tool): random per run, shown to the model in the
# preview tool result and echoed back as ``confirm_token``. Normalized in the request key; in
# the recorded response it becomes a placeholder re-filled from the replayed prompt's token.
_PENDING_TOKEN = re.compile(r"\(token: ([A-Za-z0-9_-]+)\)")
# The same pending deletion is also echoed in the system prompt as a ``pending_delete`` JSON
# line carrying the token plus clock-derived ``expires_at`` / ``created_turn``.
_PENDING_JSON = re.compile(r'("token": ")([A-Za-z0-9_-]+)(", "expires_at": )[\d.]+(, "created_turn": )\d+')


def _last_token(messages: list[BaseMessage]) -> str | None:
    for m in reversed(messages):
        found = _PENDING_TOKEN.findall(str(m.content)) or [x[1] for x in _PENDING_JSON.findall(str(m.content))]
        if found:
            return found[-1]
    return None


class CassetteStale(RuntimeError):
    pass


def _iso_to_offset(text: str, base: date, fmt: str) -> str:
    def sub(m: re.Match) -> str:
        try:
            d = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return m[0]
        return fmt.format((d - base).days)

    return _ISO_DATE.sub(sub, text)


def normalize_text(text: str, base: date) -> str:
    """Stable form of a prompt string (see module docstring)."""
    text = _UUID.sub("<UUID>", text)
    text = _PENDING_TOKEN.sub("(token: <TOKEN>)", text)
    text = _PENDING_JSON.sub(r"\1<TOKEN>\3<T>\4<T>", text)
    text = _iso_to_offset(text, base, "D{:+d}")
    out = []
    for line in text.split("\n"):
        if _VOLATILE_LINE.match(line):
            line = _TIME.sub("<T>", _WEEKDAY.sub("<WD>", _PT_DATE.sub("<DATE>", line)))
        out.append(line)
    return "\n".join(out)


def _norm(obj: Any, base: date) -> Any:
    if isinstance(obj, str):
        return normalize_text(obj, base)
    if isinstance(obj, list):
        return [_norm(x, base) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _norm(v, base) for k, v in sorted(obj.items())}
    return obj


def _tool_spec(tool: Any) -> dict:
    if isinstance(tool, dict):  # already an OpenAI-style schema
        spec = tool.get("function", tool)
        return {"name": spec.get("name"), "description": spec.get("description"), "parameters": spec.get("parameters") or {}}
    # BaseTool: name + description + argument schema (no convert_to_openai_tool: keeps this
    # module independent of langchain_core internals that unit tests stub out)
    return {"name": getattr(tool, "name", str(tool)), "description": getattr(tool, "description", ""), "parameters": getattr(tool, "args", {})}


def request_payload(messages: list[BaseMessage], tools: list | None, base: date) -> dict:
    msgs = []
    for m in messages:
        item: dict[str, Any] = {"role": m.type, "content": _norm(m.content, base)}
        calls = getattr(m, "tool_calls", None)
        if calls:
            item["tool_calls"] = [
                {"name": c["name"], "args": _norm({k: ("<TOKEN>" if k == "confirm_token" and v else v) for k, v in (c.get("args") or {}).items()}, base)}
                for c in calls
            ]
        if m.type == "tool" and getattr(m, "name", None):
            item["name"] = m.name
        msgs.append(item)
    return {"messages": msgs, "tools": [_tool_spec(t) for t in tools or []]}


def request_key(messages: list[BaseMessage], tools: list | None, base: date) -> str:
    payload = request_payload(messages, tools, base)
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _swap_token(args: dict, value: str | None) -> dict:
    if not value:
        return args
    return {k: (value if k == "confirm_token" and v else v) for k, v in args.items()}


def encode_response(msg: AIMessage, base: date, token: str | None = None) -> dict:
    raw = {
        "content": msg.content,
        "tool_calls": [
            {"name": c["name"], "args": _swap_token(c.get("args") or {}, "@@TOKEN@@" if token else None), "id": c.get("id")}
            for c in msg.tool_calls
        ],
    }
    return json.loads(_iso_to_offset(json.dumps(raw, ensure_ascii=False), base, "@@D{:+d}@@"))


def decode_response(raw: dict, base: date, token: str | None = None) -> AIMessage:
    blob = _TOKEN.sub(lambda m: (base + timedelta(days=int(m[1]))).isoformat(), json.dumps(raw, ensure_ascii=False))
    data = json.loads(blob)
    calls = [
        {
            "name": c["name"],
            "args": {k: (token if v == "@@TOKEN@@" and token else v) for k, v in (c.get("args") or {}).items()},
            "id": c.get("id") or f"sim-{i}",
            "type": "tool_call",
        }
        for i, c in enumerate(data.get("tool_calls") or [])
    ]
    return AIMessage(content=data.get("content", ""), tool_calls=calls)


def _today() -> date:
    return datetime.now().date()  # container clock (libfaketime + TZ) = the sim clock


class _Cassette:
    """Process-wide state for the active scenario attempt."""

    def __init__(self, directory: Path):
        self.dir = directory
        self.lock = threading.Lock()
        self.nonce: str | None = None
        self.scenario: str | None = None
        self.entries: dict[str, list[dict]] = {}
        self.cursor: dict[str, int] = {}

    def _sync(self, record: bool) -> None:
        try:
            ctl = json.loads((self.dir / "ctl").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise CassetteStale(f"{STALE_MSG} (no active cassette: runner did not announce a scenario)") from None
        if ctl.get("nonce") == self.nonce:
            return
        self.nonce, self.scenario = ctl.get("nonce"), ctl.get("id")
        self.entries, self.cursor = {}, {}
        path = self.dir / f"{self.scenario}.jsonl"
        if record:
            path.write_text("", encoding="utf-8")
        elif path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.entries.setdefault(row["key"], []).append(row["response"])

    def lookup(self, key: str, preview: str) -> dict:
        with self.lock:
            self._sync(record=False)
            rows = self.entries.get(key) or []
            i = self.cursor.get(key, 0)
            if i >= len(rows):  # unknown key, or asked more times than recorded
                why = "unrecorded prompt" if not rows else f"asked {i + 1}x, recorded {len(rows)}x"
                msg = f"{STALE_MSG} ({why}; scenario {self.scenario}, key {key[:12]}, prompt tail: {preview[:120]!r})"
                with open(self.dir / STALE_LOG, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
                raise CassetteStale(msg)
            self.cursor[key] = i + 1
            return rows[i]

    def append(self, key: str, preview: str, response: dict) -> None:
        with self.lock:
            self._sync(record=True)
            row = {"key": key, "prompt_tail": _iso_to_offset(preview[:200], _today(), "D{:+d}"), "response": response}
            with open(self.dir / f"{self.scenario}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


_STATE: _Cassette | None = None


def _state() -> _Cassette:
    global _STATE
    if _STATE is None:
        _STATE = _Cassette(CASSETTE_DIR)
    return _STATE


def _preview(messages: list[BaseMessage]) -> str:
    return str(messages[-1].content) if messages else ""


class SimCassetteChatModel(BaseChatModel):
    """Chat model that records (``inner`` set) or replays (``inner`` None) cassette answers."""

    inner: Any = None

    @property
    def _llm_type(self) -> str:
        return "sim-record" if self.inner is not None else "sim-replay"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: ANN001
        extra = dict(kwargs)
        if tool_choice is not None:
            extra["tool_choice"] = tool_choice
        return self.bind(tools=list(tools), **extra)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001
        tools = kwargs.pop("tools", None)
        base = _today()
        key = request_key(messages, tools, base)
        st = _state()
        if self.inner is None:
            msg = decode_response(st.lookup(key, _preview(messages)), base, _last_token(messages))
        else:
            model = self.inner.bind_tools(tools, **kwargs) if tools else self.inner
            msg = model.invoke(messages, stop=stop)
            st.append(key, _preview(messages), encode_response(msg, base, _last_token(messages)))
        return ChatResult(generations=[ChatGeneration(message=msg)])


_CLOCK_STAMP = re.compile(r"\b\d{1,2}:\d{2}\b")
_TODAY_LINE = re.compile(r"Hoje é [^,\n]+,")
_DAY_MONTH = re.compile(r"\b\d{1,2}/\d{1,2}\b")


def structured_key(task: str, prompt: str, schema: dict, base: date) -> str:
    """Key of a ``llm_structured.run_structured`` call. Like chat requests, the day-dependent
    parts of the prompt are normalized (ISO dates -> offsets, weekday names, ``dd/mm`` and
    ``HH:MM`` stamps; only the "Hoje é <weekday>," header, never the chat text) so a cassette recorded on one day replays on any other."""
    text = _CLOCK_STAMP.sub("<T>", _DAY_MONTH.sub("<DM>", _TODAY_LINE.sub("Hoje é <WD>,", normalize_text(prompt, base))))
    blob = json.dumps({"task": task, "prompt": text, "schema": schema}, sort_keys=True, ensure_ascii=False)
    return "structured:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def structured_call(mode: str, task: str, prompt: str, schema: dict, call) -> dict | None:  # noqa: ANN001
    """Record (``call()`` is the real provider call) or replay one structured answer."""
    key = structured_key(task, prompt, schema, _today())
    st = _state()
    if os.getenv("EVI_SIM_DUMP_STRUCTURED", "").strip() == "1":  # debug: full prompt per call, to diff stale keys
        try:
            (CASSETTE_DIR / f"dump-{key[11:23]}-{mode}.txt").write_text(prompt, encoding="utf-8")
        except OSError:
            pass
    if mode == "replay":
        return st.lookup(key, prompt[-200:])
    out = call()
    if isinstance(out, dict):  # failures are not recorded: a replay then reports it stale
        st.append(key, prompt[-200:], out)
    return out


def build_sim_llm(provider: str, *, temperature: float | None = None):
    """Factory used by ``llm.build_llm`` (only reachable with EVI_SIM=1)."""
    if provider == "sim-record":
        from llm import build_llm

        return SimCassetteChatModel(inner=build_llm(provider="gemini", temperature=temperature))
    return SimCassetteChatModel()
