"""Scheduled tasks (evi-scheduled-tasks): a question EVI answers by itself on a schedule.

Storage + caps live here (create/list/cancel/pause/resume, 10 active, 6 runs per local
day); ``run_due`` is the loop hook that claims due rows, runs each one in a read-only
turn (channel ``scheduled``, session ``scheduled:<id>``, only ``read_only_tools()``
bound) on its own single-worker executor with a 90 s timeout, and delivers the answer to
Telegram. Recurrence reuses ``reminders.next_occurrence`` / presets.
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable

import db
from services.soft_fail import soft_fail
from tools.calendar_time import now_local

MAX_ACTIVE = 10
MAX_RUNS_PER_DAY = 6
RUN_TIMEOUT_S = 90.0
TITLE_WORDS = 6
TITLE_MAX = 60

_FALSE = {"0", "false", "no", "off"}
_DISABLED = "Tarefas agendadas estão desativadas (EVI_SCHEDULED_TASKS_ENABLED)."
SCHEDULED_ADDENDUM = (
    "Execução agendada pelo usuário: responda direto, sem perguntas de volta. "
    "Só consulta (leitura); não há ferramentas para criar, apagar ou enviar nada."
)
# Tools a scheduled turn never gets, on top of WRITE_TOOLS: scheduling about scheduling.
_SCHEDULING_TOOLS = frozenset(
    {
        "create_reminder",
        "list_reminders",
        "cancel_reminder",
        "snooze_reminder",
        "complete_reminder",
        "create_scheduled_task",
        "list_scheduled_tasks",
        "cancel_scheduled_task",
        "pause_scheduled_task",
        "resume_scheduled_task",
    }
)


# Read tools that are NOT pure reads: get_whatsapp_contact_info can backfill the contact's
# history, run LLM extraction, queue commitments and notify; list_whatsapp_contacts refreshes
# the local registry from Evolution. Scheduled turns never get them.
SIDE_EFFECT_READ_TOOLS = frozenset({"get_whatsapp_contact_info", "list_whatsapp_contacts"})


def enabled() -> bool:
    """EVI_SCHEDULED_TASKS_ENABLED (default on), read at call time."""
    return os.getenv("EVI_SCHEDULED_TASKS_ENABLED", "true").strip().lower() not in _FALSE


# --- helpers ------------------------------------------------------------------


def derive_title(prompt: str) -> str:
    words = (prompt or "").split()
    title = " ".join(words[:TITLE_WORDS])
    if len(words) > TITLE_WORDS:
        title += "…"
    return title[:TITLE_MAX] or "Tarefa"


def _local_day(dt: datetime):
    from services.reminders import _tz

    return dt.astimezone(_tz()).date()


def _fmt(dt: datetime) -> str:
    from tools.reminder_tools import _fmt_full

    return _fmt_full(dt)


def _repeat_suffix(repeat: str | None) -> str:
    from tools.reminder_tools import _REPEAT_LABEL

    return f" ({_REPEAT_LABEL[repeat]})" if repeat in _REPEAT_LABEL else ""


def _init() -> None:
    db.init_db()


# --- CRUD ---------------------------------------------------------------------


def create(
    prompt: str, due_at, repeat: str = "", title: str | None = None, now: datetime | None = None
) -> tuple[dict | None, str]:
    """Store a task. Returns ``(task_row | None, message)``; refuses past/invalid times,
    unknown repeats and the 11th active task with a clear message."""
    if not enabled():
        return None, _DISABLED
    from services.reminders import validate_new

    prompt = (prompt or "").strip()
    if not prompt:
        return None, "Não criei a tarefa: a pergunta está vazia."
    rep = (repeat or "").strip().lower() or None
    now = now or now_local()
    try:
        due, err = validate_new(prompt, due_at, rep, now)
    except Exception as exc:  # noqa: BLE001
        return None, f"Não consegui validar a tarefa: {exc}"
    if err:
        return None, f"Não criei a tarefa: {err}"
    try:
        _init()
        title = (title or "").strip()[:TITLE_MAX] or derive_title(prompt)
        tid = db.create_scheduled_task(title, prompt, due, rep, max_active=MAX_ACTIVE)
        if tid is None:  # cap checked atomically with the insert
            return None, (
                f"Já existem {MAX_ACTIVE} tarefas agendadas ativas (o máximo). "
                "Cancele ou pause uma antes de criar outra."
            )
        row = db.get_scheduled_task(tid)
    except Exception as exc:  # noqa: BLE001
        return None, f"Não consegui salvar a tarefa: {exc}"
    return row, f"Tarefa agendada #{tid} «{title}» para {_fmt(due)}{_repeat_suffix(rep)}."


def list_tasks() -> list[dict]:
    _init()
    return db.list_scheduled_tasks()


def format_list() -> str:
    if not enabled():
        return _DISABLED
    try:
        rows = list_tasks()
    except Exception as exc:  # noqa: BLE001
        return f"Não consegui listar as tarefas: {exc}"
    if not rows:
        return "Nenhuma tarefa agendada."
    lines = []
    for r in rows:
        state = "" if r["active"] else " [pausada]"
        lines.append(
            f"#{r['id']} «{r['title']}» — {_fmt(r['next_at'])}{_repeat_suffix(r.get('repeat'))}{state}"
        )
    return "\n".join(lines)


def find(id_or_title: str | int) -> tuple[dict | None, str]:
    """Resolve by id, exact title, then unique substring of the title."""
    ref = str(id_or_title).strip()
    if not ref:
        return None, "Diga o número ou o título da tarefa."
    _init()
    rows = db.list_scheduled_tasks()
    if ref.lstrip("#").isdigit():
        want = int(ref.lstrip("#"))
        for r in rows:
            if r["id"] == want:
                return r, ""
        return None, f"Tarefa #{want} não encontrada."
    low = ref.lower()
    exact = [r for r in rows if r["title"].lower() == low]
    hits = exact or [r for r in rows if low in r["title"].lower()]
    if len(hits) == 1:
        return hits[0], ""
    if not hits:
        return None, f"Não achei tarefa agendada «{ref}»."
    opts = "; ".join(f"#{r['id']} «{r['title']}»" for r in hits[:5])
    return None, f"Mais de uma tarefa combina com «{ref}»: {opts}. Use o número."


def cancel(id_or_title) -> tuple[bool, str]:
    if not enabled():
        return False, _DISABLED
    try:
        row, err = find(id_or_title)
        if row is None:
            return False, err
        db.delete_scheduled_task(row["id"])
    except Exception as exc:  # noqa: BLE001
        return False, f"Não consegui cancelar a tarefa: {exc}"
    return True, f"Tarefa #{row['id']} «{row['title']}» cancelada."


def pause(id_or_title) -> tuple[bool, str]:
    if not enabled():
        return False, _DISABLED
    try:
        row, err = find(id_or_title)
        if row is None:
            return False, err
        db.set_scheduled_task_active(row["id"], False)
    except Exception as exc:  # noqa: BLE001
        return False, f"Não consegui pausar a tarefa: {exc}"
    return True, f"Tarefa #{row['id']} «{row['title']}» pausada."


def resume(id_or_title, now: datetime | None = None) -> tuple[bool, str]:
    """Reactivate; a recurring task moves to its next occurrence after now (never fires
    for the time it was paused). A one-off whose time passed cannot be resumed."""
    if not enabled():
        return False, _DISABLED
    from services.reminders import next_occurrence

    now = now or now_local()
    try:
        row, err = find(id_or_title)
        if row is None:
            return False, err
        if row["active"]:
            return True, f"Tarefa #{row['id']} «{row['title']}» já está ativa."
        nxt = row["next_at"]
        if nxt <= now:
            if not row.get("repeat"):
                return False, "Esse horário já passou; crie a tarefa de novo com um novo horário."
            nxt = next_occurrence(nxt, row["repeat"], now)
        if not db.set_scheduled_task_active(row["id"], True, nxt, max_active=MAX_ACTIVE):
            return False, f"Já existem {MAX_ACTIVE} tarefas ativas; cancele ou pause outra antes."
    except Exception as exc:  # noqa: BLE001
        return False, f"Não consegui retomar a tarefa: {exc}"
    return True, f"Tarefa #{row['id']} «{row['title']}» retomada; próxima: {_fmt(nxt)}."


# --- read-only turn -------------------------------------------------------------


def read_only_tools() -> list:
    """Every registered tool minus WRITE_TOOLS, reminder/scheduling tools and
    SIDE_EFFECT_READ_TOOLS."""
    from services.write_guard import WRITE_TOOLS
    from tools.registry import get_all_tools

    return [
        t for t in get_all_tools() if t.name not in WRITE_TOOLS
        and t.name not in _SCHEDULING_TOOLS
        and t.name not in SIDE_EFFECT_READ_TOOLS
    ]


_graph_cache: Any = None
_graph_lock = threading.Lock()


def _graph():
    """The read-only graph, built once (separate from the chat graph in main)."""
    global _graph_cache
    with _graph_lock:
        if _graph_cache is None:
            from graph import build_agent_graph

            _graph_cache = build_agent_graph(read_only_tools())
        return _graph_cache


def run_turn(task: dict) -> str:
    """Run one task's question as a fresh scheduled turn and return the answer text.

    channel ``scheduled`` (the write guard refuses any write in it), session
    ``scheduled:<id>``, no chat history. Raises on failure; records a turn_log row.

    ``task["cancel"]`` (a threading.Event set by the executor on timeout) marks an
    abandoned run: the in-flight LLM/tool call cannot be interrupted, so when it finally
    returns the result is dropped and no turn_log row is written."""
    from langchain_core.messages import HumanMessage

    from llm import extract_llm_text
    from services.turn_log import end_turn, record_turn, start_turn

    session_id = f"scheduled:{task['id']}"
    prompt = task["prompt"]
    collector, token = start_turn("scheduled", session_id, False, "text", user_text=prompt)
    started = time.monotonic()
    reply: str | None = None
    error: str | None = None
    try:
        result = _graph().invoke(
            {
                "messages": [HumanMessage(content=prompt)],
                "task_type": "scheduled",
                "iterations": 0,
                "final_answer": "",
                "extra_context": SCHEDULED_ADDENDUM,
            },
            config={"callbacks": [collector]},
        )
        msgs = result.get("messages", [])
        final = result.get("final_answer", "")
        if final:
            reply = extract_llm_text(final)
        elif msgs and msgs[-1].type == "ai":
            reply = extract_llm_text(msgs[-1].content)
        reply = (reply or "").strip()
        if not reply:
            raise RuntimeError("empty answer")
        return reply
    except Exception as exc:
        error = str(exc or type(exc).__name__)[:500]
        raise
    finally:
        end_turn(token)
        cancel = task.get("cancel")
        if not (cancel is not None and cancel.is_set()):
            record_turn(
                collector,
                session_id=session_id,
                channel="scheduled",
                user_text=prompt,
                reply_text=reply,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=error,
                is_test=False,
            )


# --- loop hook ------------------------------------------------------------------

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_inflight: set[int] = set()
_inflight_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sched-task")
        return _executor


def _call_with_timeout(fn: Callable[[dict], str], arg: dict, timeout: float) -> str:
    """(``arg["cancel"]`` is set on timeout so the abandoned run drops its result.)"""
    """Run ``fn(arg)`` in a daemon thread; a run past ``timeout`` is abandoned (it can only
    read, and its delivery never happens) so one stuck LLM call cannot block the worker."""
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["ok"] = fn(arg)
        except BaseException as exc:  # noqa: BLE001
            box["err"] = exc

    th = threading.Thread(target=target, name="sched-run", daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        cancel = arg.get("cancel")
        if cancel is not None:
            cancel.set()
        raise TimeoutError(f"scheduled run exceeded {timeout:g}s")
    if "err" in box:
        raise box["err"]
    return box["ok"]


def _notify(send: Callable[..., Any], text: str, ctx: str) -> bool:
    try:
        return bool(send(text))
    except Exception as exc:  # noqa: BLE001
        soft_fail(ctx, exc)
        return False


def _process(
    task: dict, send: Callable[..., Any], runner: Callable[[dict], str], timeout: float
) -> str:
    """Run one claimed task and deliver; returns the final status."""
    tid, title = task["id"], task["title"]
    try:
        try:
            answer = _call_with_timeout(runner, task, timeout)
        except Exception as exc:  # noqa: BLE001 (incl. TimeoutError)
            soft_fail("scheduled_tasks.run", exc, detail=f"id={tid}")
            _finish(tid, "error", None)
            tail = "; tento na próxima." if task.get("repeat") else "."
            _notify(send, f"Não consegui rodar '{title}' agora{tail}", "scheduled_tasks.notify_fail")
            return "error"
        status = "ok" if _notify(send, f"🗓 {title}\n{answer}", "scheduled_tasks.deliver") else "send_failed"
        _finish(tid, status, now_local())
        return status
    finally:
        with _inflight_lock:
            _inflight.discard(tid)


def _finish(tid: int, status: str, ran_at) -> None:
    try:
        db.finish_scheduled_task(tid, status, ran_at)
    except Exception as exc:  # noqa: BLE001
        soft_fail("scheduled_tasks.finish", exc, detail=f"id={tid}")


def run_due(
    now: datetime | None = None,
    send: Callable[..., Any] | None = None,
    runner: Callable[[dict], str] | None = None,
    wait: bool = False,
    timeout: float | None = None,
) -> dict:
    """One tick: claim due tasks and hand each to the single-worker executor.

    Never blocks on the run itself (``wait=True`` only for tests). Claiming is a CAS that
    already advances ``next_at`` (one-shots deactivate), so a task can never run twice for
    one occurrence. Over the daily cap a task is not run today: it moves to its next
    occurrence (a one-off: tomorrow, same time) and the user is told once."""
    counts = {"due": 0, "started": 0, "capped": 0, "skipped": 0}
    if not enabled():
        return counts
    from services.reminders import next_occurrence

    if send is None:
        from services.telegram_notify import send_telegram_message as send
    runner = runner or run_turn
    timeout = RUN_TIMEOUT_S if timeout is None else timeout
    now = now or now_local()
    try:
        _init()
        rows = db.due_scheduled_tasks(now)
        used = db.scheduled_runs_on(_local_day(now))
    except Exception as exc:  # noqa: BLE001
        soft_fail("scheduled_tasks.due", exc)
        return counts
    counts["due"] = len(rows)
    futures: list[Future] = []
    for row in rows:
        tid, due = row["id"], row["next_at"]
        with _inflight_lock:
            if tid in _inflight:
                counts["skipped"] += 1
                continue
            _inflight.add(tid)
        over = used >= MAX_RUNS_PER_DAY
        try:
            rep = row.get("repeat")
            if rep:
                nxt, active = next_occurrence(due, rep, now), True
            elif over:
                nxt, active = next_occurrence(due, "daily", now), True
            else:
                nxt, active = due, False
            claimed = db.claim_scheduled_task(
                tid, due, nxt, active, _local_day(now), count_run=not over
            )
        except Exception as exc:  # noqa: BLE001
            soft_fail("scheduled_tasks.claim", exc, detail=f"id={tid}")
            claimed = None
        if claimed is None:
            with _inflight_lock:
                _inflight.discard(tid)
            counts["skipped"] += 1
            continue
        if over:
            with _inflight_lock:
                _inflight.discard(tid)
            counts["capped"] += 1
            _finish(tid, "capped", None)
            # via the executor: a Telegram send never blocks the loop thread
            futures.append(
                _get_executor().submit(
                    _notify,
                    send,
                    f"Hoje já rodaram {MAX_RUNS_PER_DAY} tarefas agendadas (o limite diário); "
                    f"'{row['title']}' fica para {_fmt(nxt)}.",
                    "scheduled_tasks.notify_cap",
                )
            )
            continue
        used += 1
        counts["started"] += 1
        task = {**claimed, "next_at": due, "cancel": threading.Event()}
        futures.append(_get_executor().submit(_process, task, send, runner, timeout))
    if wait:
        for f in futures:
            f.result()
    return counts
