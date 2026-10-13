# /home/marshibs/Projects/EVI/agent/main.py
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from auth import require_api_key_configured, verify_api_key
from graph import build_agent_graph
from services.session_memory import drop_session_memory, get_session_memory
from services.soft_fail import soft_fail
from tools.note_manager import build_auto_insight, save_note_manual
from tools.registry import get_all_tools

AVAILABLE_TOOLS = get_all_tools()


class AgentApplicationState:
    graph = None
    default_session = "default"


app_state = AgentApplicationState()


def _persist_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    if not os.getenv("DATABASE_URL"):
        return
    try:
        from db import save_message

        save_message(session_id, "user", user_text)
        save_message(session_id, "assistant", assistant_text)
    except Exception as exc:
        soft_fail("main.persist_turn", exc)


def _hydrate_memory(session_id: str) -> None:
    if not os.getenv("DATABASE_URL"):
        return
    memory = get_session_memory(session_id)
    try:
        from db import load_recent_messages

        rows = load_recent_messages(session_id, limit=16)
        memory.clear()
        for row in rows:
            if row["role"] == "user":
                memory.add(HumanMessage(content=row["content"]))
            else:
                memory.add(AIMessage(content=row["content"]))
    except Exception as exc:
        soft_fail("main.hydrate_memory", exc)


def _last_turn_texts(messages: list) -> tuple[str, str]:
    """Most recent (user_text, assistant_text) pair from a message list."""
    from llm import extract_llm_text

    last_user = ""
    last_ai = ""
    for m in reversed(messages):
        if getattr(m, "type", None) == "ai" and not last_ai:
            last_ai = extract_llm_text(getattr(m, "content", ""))
        if getattr(m, "type", None) == "human" and not last_user:
            last_user = str(getattr(m, "content", ""))
        if last_user and last_ai:
            break
    return last_user, last_ai


def _flush_session_memory(session_id: str, messages: list) -> None:
    from services.memory_flush import maybe_flush_before_compaction

    last_user, last_ai = _last_turn_texts(messages)
    maybe_flush_before_compaction(
        session_id=session_id,
        messages=messages,
        user_text=last_user,
        assistant_text=last_ai,
    )


def _reset_session(session_id: str) -> None:
    drop_session_memory(session_id)


def _compact_session(session_id: str) -> None:
    memory = get_session_memory(session_id)
    msgs = memory.get_messages()
    _flush_session_memory(session_id, msgs)
    kept = msgs[-4:]
    memory.clear()
    for msg in kept:
        memory.add(msg)


def _telegram_invoke_chat(
    message: str,
    session_id: str,
    is_test: bool = False,
    input_kind: str = "text",
    forwarded: bool = False,
) -> Dict[str, Any]:
    return _run_chat(
        ChatRequest(message=message, session_id=session_id),
        session_id,
        "telegram",
        is_test,
        input_kind,
        forwarded,
    )


def _whatsapp_control_invoke_chat(
    message: str, session_id: str, input_kind: str = "text"
) -> Dict[str, Any]:
    return _run_chat(
        ChatRequest(message=message, session_id=session_id),
        session_id,
        "whatsapp_control",
        input_kind=input_kind,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    require_api_key_configured()
    app_state.graph = build_agent_graph(AVAILABLE_TOOLS)
    if os.getenv("DATABASE_URL"):
        try:
            from db import init_db

            init_db()
        except Exception as exc:
            soft_fail("main.lifespan.init_db", exc)
    if os.getenv("TELEGRAM_MODE", "").strip().lower() == "polling":
        from services.telegram_poller import start_poller

        start_poller(
            _telegram_invoke_chat,
            reset_session=_reset_session,
            compact_session=_compact_session,
        )
    from services.reminder_loop import start_loop

    if start_loop():
        print("EVI: reminder loop started")
    try:
        from pathlib import Path
        from services.log_retention import prune_logs

        prune_logs(Path(os.getenv("EVI_LOG_DIR", "/logs")))
    except Exception as exc:
        soft_fail("main.lifespan.prune_logs", exc)
    gmail_res = os.getenv("WINDMILL_GMAIL_RESOURCE", "")
    if gmail_res:
        print(f"EVI: WINDMILL_GMAIL_RESOURCE={gmail_res}", flush=True)
    yield
    try:
        from services.reminder_loop import stop_loop
        from services.telegram_poller import stop_poller

        stop_loop()
        stop_poller()
    except Exception as exc:
        soft_fail("main.lifespan.shutdown", exc)


app = FastAPI(title="EVI — Evolving Virtual Intelligence", lifespan=lifespan)

from services.metrics import PrometheusMiddleware  # noqa: E402

app.add_middleware(PrometheusMiddleware)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class TaskRequest(BaseModel):
    task: str
    params: Dict[str, Any] = {}


class NoteRequest(BaseModel):
    title: str
    content: str
    tags: List[str] = []
    category: str = "general"


class InsightRequest(BaseModel):
    session_id: Optional[str] = None


class ResetRequest(BaseModel):
    session_id: Optional[str] = None


class TelegramUpdate(BaseModel):
    message: Optional[Dict[str, Any]] = None


@app.get("/")
def root():
    return {
        "status": "EVI is alive",
        "services": ["graph", "tools", "postgres" if os.getenv("DATABASE_URL") else "memory-only"],
    }


@app.get("/health")
def health():
    from services.health import run_health_checks

    return run_health_checks(graph_ready=app_state.graph is not None)


@app.get("/metrics")
def metrics(_: None = Depends(verify_api_key)):
    from services.metrics import metrics_response

    return metrics_response()


@app.get("/tools")
def list_tools(_: None = Depends(verify_api_key)):
    return {"tools": [t.name for t in AVAILABLE_TOOLS]}


@app.post("/reset")
def reset_memory(
    request: Optional[ResetRequest] = None,
    x_session_id: Optional[str] = Header(default=None),
    _: None = Depends(verify_api_key),
):
    session_id = (
        (request.session_id if request else None)
        or x_session_id
        or app_state.default_session
    )
    existed = drop_session_memory(session_id)
    return {"status": "Memory wiped.", "session_id": session_id, "existed": existed}


@app.post("/chat")
def chat(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(default=None),
    x_evi_test: Optional[str] = Header(default=None),
    _: None = Depends(verify_api_key),
):
    session_id = request.session_id or x_session_id or app_state.default_session
    return _run_chat(request, session_id, "api", _header_is_test(x_evi_test))


def _header_is_test(value: Optional[str]) -> bool:
    """`X-Evi-Test: 1` marks a harness turn (excluded from every KPI)."""
    return isinstance(value, str) and value.strip().lower() in ("1", "true")


def _run_chat(
    request: ChatRequest,
    session_id: str,
    channel: str,
    is_test: bool = False,
    input_kind: str = "text",
    forwarded: bool = False,
) -> Dict[str, Any]:
    """Single entry for every turn (HTTP, Telegram, WhatsApp control); `channel`
    is only used to label the turn_log row."""
    if not app_state.graph:
        raise HTTPException(status_code=500, detail="Agent graph not initialized")

    from services.session_lane import session_lane

    with session_lane(session_id):
        return _chat_impl(request, session_id, channel, is_test, input_kind, forwarded)


def _chat_impl(
    request: ChatRequest,
    session_id: str,
    channel: str = "api",
    is_test: bool = False,
    input_kind: str = "text",
    forwarded: bool = False,
) -> Dict[str, Any]:
    from services.turn_log import end_turn, record_turn, start_turn

    # A forwarded message is not the user's own words: it can never confirm or
    # justify a deletion, so the guard sees an empty user text for this turn.
    collector, token = start_turn(
        channel,
        session_id,
        is_test,
        input_kind,
        user_text="" if forwarded else request.message,
    )
    started = time.monotonic()
    reply: Optional[str] = None
    error: Optional[str] = None
    try:
        result = _chat_turn(request, session_id, collector)
        reply = result.get("response")
        return result
    except Exception as exc:
        error = str(getattr(exc, "detail", None) or exc or type(exc).__name__)[:500]
        raise
    finally:
        end_turn(token)
        record_turn(
            collector,
            session_id=session_id,
            channel=channel,
            user_text=request.message,
            reply_text=reply,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=error,
            is_test=is_test,
        )


def _append_delete_preview(text: str, collector) -> str:
    """When this turn staged an e-mail deletion, append a fixed, code-built preview
    after the model's text (the model is not trusted to show what will be deleted)."""
    pend = getattr(collector, "pending_preview", None)
    if not pend:
        return text
    count = int(pend.get("count") or 0)
    shown = [s for s in (pend.get("subjects") or []) if s][:5]
    lines = [f"🗑️ Vou mover {count} e-mail(s) para a lixeira:"]
    lines += [f"• {s}" for s in shown]
    if count > len(shown):
        lines.append(f"… e mais {count - len(shown)} outros")
    lines.append("Responda «sim» para confirmar.")
    return f"{text}\n\n" + "\n".join(lines)


def _chat_turn(request: ChatRequest, session_id: str, collector) -> Dict[str, Any]:
    _hydrate_memory(session_id)

    from services.context_assembly import build_context
    from services.session_context import persist_tool_snapshots, summarize_tool_calls

    memory = get_session_memory(session_id)
    extra_context = build_context(session_id, request.message)

    def _on_trim() -> None:
        _flush_session_memory(session_id, memory.get_messages())

    memory.set_on_trim(_on_trim)

    user_message = HumanMessage(content=request.message)
    memory.add(user_message)

    initial_state = {
        "messages": memory.get_messages(),
        "task_type": "chat",
        "iterations": 0,
        "final_answer": "",
        "extra_context": extra_context,
    }

    try:
        result = app_state.graph.invoke(initial_state, config={"callbacks": [collector]})
        output_messages = result.get("messages", [])
        final_answer = result.get("final_answer", "")

        from llm import extract_llm_text

        if final_answer:
            ai_content = extract_llm_text(final_answer)
        elif output_messages and output_messages[-1].type == "ai":
            ai_content = extract_llm_text(output_messages[-1].content)
        else:
            ai_content = "The agent returned an empty response."

        ai_content = _append_delete_preview(ai_content, collector)

        tool_audit = summarize_tool_calls(output_messages)
        persist_tool_snapshots(session_id, output_messages)

        memory.clear()
        for msg in output_messages[-16:]:
            memory.add(msg)

        _persist_turn(session_id, request.message, ai_content)
        return {
            "response": ai_content,
            "session_id": session_id,
            "tools": tool_audit,
            "output_messages": output_messages,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/note")
def save_note(request: NoteRequest, _: None = Depends(verify_api_key)):
    try:
        path = save_note_manual.invoke(
            {
                "title": request.title,
                "content": request.content,
                "tags": request.tags,
                "category": request.category,
            }
        )
        return {"path": path, "status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/insight")
def generate_insight(request: InsightRequest, _: None = Depends(verify_api_key)):
    session_id = request.session_id or app_state.default_session
    turns = []
    for msg in get_session_memory(session_id).get_messages():
        turns.append(
            {"role": "user" if msg.type == "human" else "assistant", "content": msg.content}
        )
    if not turns and os.getenv("DATABASE_URL"):
        try:
            from db import load_recent_messages

            for row in load_recent_messages(session_id, limit=8):
                turns.append({"role": row["role"], "content": row["content"]})
        except Exception as exc:
            soft_fail("main.insight.load_recent_messages", exc)
    try:
        path = build_auto_insight(turns, session_id=session_id)
        return {"path": path, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhooks/telegram")
def telegram_webhook(
    update: TelegramUpdate,
    x_evi_test: Optional[str] = Header(default=None),
    _: None = Depends(verify_api_key),
):
    """Telegram webhook → EVI chat (use TELEGRAM_MODE=polling to skip tunnel)."""
    from services.telegram_handler import process_telegram_update

    payload = update.model_dump() if hasattr(update, "model_dump") else {"message": update.message}
    flagged = _header_is_test(x_evi_test)
    return process_telegram_update(
        payload,
        (lambda m, sid, input_kind="text", forwarded=False: _telegram_invoke_chat(m, sid, True, input_kind, forwarded)) if flagged else _telegram_invoke_chat,
        reset_session=_reset_session,
        compact_session=_compact_session,
    )


@app.post("/webhooks/evolution")
def evolution_webhook(
    body: Dict[str, Any],
    _: None = Depends(verify_api_key),
):
    """Evolution API MESSAGES_UPSERT → commitment extraction."""
    import time
    from pathlib import Path

    from services.metrics import observe_webhook

    _wh_start = time.perf_counter()
    from services.evolution_filter import claim_message_id, filter_for_processing
    from services.evolution_parser import parse_evolution_webhook
    from services.whatsapp_processor import WhatsAppProcessor

    from datetime import datetime, timezone

    from services.log_retention import append_jsonl, trim_jsonl

    log_dir = Path(os.getenv("EVI_LOG_DIR", "/tmp/evi-logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "evolution_webhook.jsonl"
    ts = datetime.now(timezone.utc).isoformat()
    event = body.get("event") or body.get("type") or "unknown"
    try:
        from services.payload_shapes import capture as capture_payload_shape

        capture_payload_shape(body)
    except Exception as exc:  # noqa: BLE001
        soft_fail("main.evolution_webhook.payload_shape", exc)
    raw = parse_evolution_webhook(body)
    from services.evolution_client import is_evi_bot_message
    from services.whatsapp_control import (
        parse_control_jids,
        process_whatsapp_control_message,
    )

    control_jids = parse_control_jids()
    control_results: list[dict] = []
    ingest_raw = []
    audio_activity = []
    for msg in raw:
        if msg.sender in control_jids and msg.is_group and not msg.from_me:
            # F7: in a control GROUP only the owner's own account (fromMe) commands
            # the agent; other participants never get the whatsapp_control channel.
            append_jsonl(
                log_path,
                {
                    "ts": ts,
                    "step": "skip",
                    "event": event,
                    "hint": "control_group_not_owner",
                    "sender": msg.sender,
                    "source_id": msg.id,
                },
            )
            continue
        if msg.sender in control_jids:
            if is_evi_bot_message(msg.text):
                append_jsonl(
                    log_path,
                    {
                        "ts": ts,
                        "step": "skip",
                        "event": event,
                        "hint": "evi_echo",
                        "sender": msg.sender,
                    },
                )
                continue
            if not claim_message_id(msg.id, log_dir=log_dir):
                append_jsonl(
                    log_path,
                    {
                        "ts": ts,
                        "step": "skip",
                        "event": event,
                        "hint": "duplicate_control",
                        "source_id": msg.id,
                        "sender": msg.sender,
                        "raw_preview": msg.text[:80],
                    },
                )
                continue
            append_jsonl(
                log_path,
                {
                    "ts": ts,
                    "step": "control_in",
                    "event": event,
                    "source_id": msg.id,
                    "message_ts": msg.ts or "",
                    "sender": msg.sender,
                    "from_me": msg.from_me,
                    "raw_preview": msg.text[:80],
                },
            )
            result = process_whatsapp_control_message(
                jid=msg.sender,
                text=msg.text,
                kind=msg.kind,
                audio_seconds=msg.audio_seconds,
                audio_mime=msg.audio_mime or "audio/ogg",
                media_key=msg.media_key,
                invoke_chat=_whatsapp_control_invoke_chat,
                reset_session=_reset_session,
                compact_session=_compact_session,
            )
            control_results.append(result)
            append_jsonl(
                log_path,
                {
                    "ts": ts,
                    "step": "control_out",
                    "event": event,
                    "sender": msg.sender,
                    "whatsapp_sent": result.get("whatsapp_sent"),
                    "review_direct": result.get("review_direct"),
                    "response_preview": (result.get("response") or "")[:120],
                    "error": result.get("error"),
                },
            )
        elif msg.kind == "audio":
            # Third-party voice notes: never downloaded or transcribed (SCN-VOICE-05).
            # Only recorded as inbound activity ("[áudio]") for reply debts.
            audio_activity.append(msg)
        else:
            ingest_raw.append(msg)

    try:
        from services.reply_debts import track_conversation
        from services.whatsapp_processor import reply_debts_enabled

        track_conversation(ingest_raw + audio_activity)
        if reply_debts_enabled():
            from services.promises import capture_promises

            capture_promises(ingest_raw)
    except Exception as exc:  # noqa: BLE001
        soft_fail("main.evolution_webhook.reply_debts", exc)

    messages, filter_stats, dropped = filter_for_processing(ingest_raw, log_dir=log_dir)

    for item in dropped:
        append_jsonl(
            log_path,
            {
                "ts": ts,
                "step": "filtered_out",
                "event": event,
                **item,
            },
        )

    if messages:
        proc = WhatsAppProcessor(log_path=log_path)
        proc.log({"step": "filter", "event": event, **filter_stats})
        commitments = proc.process_messages(messages)
        try:
            from services.message_timeline import record_whatsapp_messages

            record_whatsapp_messages(messages)
        except Exception as exc:
            soft_fail("main.evolution_webhook.record_timeline", exc)
        proc.flush_log()
    else:
        commitments = []
        entry = {
            "ts": ts,
            "step": "skip",
            "event": event,
            "parsed": len(raw),
            **filter_stats,
        }
        if event == "messages.upsert" and len(raw) == 0:
            entry["hint"] = "parser_empty_text_or_unsupported_type"
        elif event == "messages.upsert" and len(raw) > 0 and filter_stats["received"] == 0:
            entry["hint"] = "all_control_channel"
        append_jsonl(log_path, entry)
    rows = [c.to_golden_row() for c in commitments]
    queued_ids: list[int] = []
    try:
        from db import init_db, insert_pending_commitment
        from services.whatsapp_processor import commitment_status_for

        init_db()
        msg_by_id = {m.id: m for m in messages}
        for c in commitments:
            raw = msg_by_id.get(c.source_id)
            raw_text = raw.text if raw else ""
            c_status = commitment_status_for(c)
            row_id = insert_pending_commitment(
                source="evolution",
                source_id=c.source_id,
                ctype=c.type,
                title=c.title,
                event_date=c.date,
                event_time=c.time,
                due_date=c.due,
                priority=c.priority,
                raw_text=raw_text,
                source_chat=raw.sender if raw else "",
                source_label=raw.label if raw else "",
                status=c_status,
            )
            if row_id and c_status == "pending":
                queued_ids.append(row_id)
                try:
                    from services.contact_filesystem import ingest_commitment

                    ingest_commitment(
                        jid=raw.sender if raw else "",
                        source_id=c.source_id,
                        title=c.title,
                        raw_text=raw_text,
                        commitment_id=row_id,
                        label=raw.label if raw else "",
                    )
                except Exception as exc:
                    soft_fail("main.evolution_webhook.ingest_commitment", exc)
                try:
                    from services.graph_sync import sync_commitment

                    sync_commitment(
                        commitment_id=row_id,
                        jid=raw.sender if raw else "",
                        title=c.title,
                        ctype=c.type,
                        status="pending",
                        label=raw.label if raw else "",
                    )
                except Exception as exc:
                    soft_fail("main.evolution_webhook.graph_sync", exc)
                try:
                    from services.commitment_capture_notify import (
                        notify_commitment_captured,
                    )

                    notify_commitment_captured(row_id, c.title, c.type)
                except Exception as exc:
                    soft_fail("main.evolution_webhook.capture_notify", exc)
        try:
            from services.commitment_review import maybe_notify_new_pending

            maybe_notify_new_pending(
                queued_ids, [c.priority for c in commitments]
            )
        except Exception as notify_exc:
            append_jsonl(
                log_path,
                {
                    "ts": ts,
                    "step": "notify_error",
                    "error": str(notify_exc)[:200],
                },
            )
    except Exception as exc:
        append_jsonl(
            log_path,
            {"ts": ts, "step": "queue_error", "error": str(exc)[:200]},
        )

    trim_jsonl(log_path, max_lines=int(os.getenv("EVI_LOG_MAX_LINES", "5000") or "5000"))
    try:
        from services.log_retention import prune_harness_logs

        prune_harness_logs(log_dir)
    except Exception as exc:
        soft_fail("main.evolution_webhook.prune_harness_logs", exc)

    observe_webhook("evolution", time.perf_counter() - _wh_start)

    return {
        "ok": True,
        "received": filter_stats["received"],
        "ingested": len(messages),
        "filter": filter_stats,
        "commitments": rows,
        "queued": len(queued_ids),
        "queued_ids": queued_ids,
        "control": control_results,
    }


@app.post("/jobs/daily-summary")
def daily_summary_job(_: None = Depends(verify_api_key)):
    """Windmill cron target: write per-contact daily summaries."""
    from services.daily_summary import run_daily_summaries

    written = run_daily_summaries()
    return {"ok": True, "written": written}


@app.post("/jobs/heartbeat")
def heartbeat_job(_: None = Depends(verify_api_key)):
    """Windmill cron target: run HEARTBEAT.md checklist."""
    from services.heartbeat import run_heartbeat

    return run_heartbeat()


@app.post("/jobs/usage-report")
def usage_report_job(week: Optional[str] = None, _: None = Depends(verify_api_key)):
    """Windmill cron target (Monday 00:30, week that just closed): weekly usage report. `?week=YYYY-Www` overrides."""
    from services.usage_report import generate_report

    try:
        return generate_report(week=week)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/jobs/usage-signals")
def usage_signals_job(_: None = Depends(verify_api_key)):
    """Windmill cron target (nightly): recompute implicit signals (last 2 days) + prune."""
    from services.usage_report import run_signals_job

    return {"ok": True, **run_signals_job()}


@app.post("/jobs/probe")
def probe_job(wait: bool = False, _: None = Depends(verify_api_key)):
    """Windmill cron target (06:30): read-only integration probe, one warning/day per failing check.

    Runs in the background and returns `{"status": "accepted"}` at once: the probe calls back
    into Windmill, whose single worker is busy running the calling script. `?wait=true` runs inline.
    """
    from services.background_jobs import run_in_background, run_inline
    from services.probe import run_probe

    if wait:
        return run_inline("probe", run_probe)
    return run_in_background("probe", run_probe)


def _briefing_work(kind: str, force: bool) -> Dict[str, Any]:
    from services.briefing import deliver_briefing

    try:
        result = deliver_briefing(kind=kind, force=force)
    except Exception as exc:
        soft_fail("jobs.briefing", exc)
        return {"status": "failed", "kind": kind, "reason": str(exc)[:200]}
    return {"kind": kind, **result}


@app.post("/jobs/briefing")
def briefing_job(
    kind: str = "morning", force: bool = False, wait: bool = False, _: None = Depends(verify_api_key)
):
    """Windmill cron target: deliver the morning/evening briefing to Telegram.

    Idempotent per (local day, kind); `?force=true` resends. Runs in the background and returns
    `{"status": "accepted"}` at once (the briefing calls back into Windmill, which has a single
    worker); `?wait=true` runs inline and returns the delivery result. Inline send failures come
    back as `{"status": "failed"}` with HTTP 200 (never a 5xx).
    """
    from services.background_jobs import run_in_background, run_inline
    from services.heartbeat import _briefing_enabled

    if kind not in {"morning", "evening"}:
        raise HTTPException(status_code=400, detail="kind must be 'morning' or 'evening'")
    if not _briefing_enabled():
        return {"status": "disabled", "kind": kind}
    if wait:
        return run_inline("briefing", _briefing_work, kind=kind, force=force)
    return run_in_background("briefing", _briefing_work, kind=kind, force=force)


class ImportContactsRequest(BaseModel):
    path: str
    apply: bool = False


@app.post("/jobs/import-contacts")
def import_contacts_job(
    request: ImportContactsRequest, _: None = Depends(verify_api_key)
):
    """Import address-book names from a local .vcf. Dry-run unless apply=true.

    The file is read from disk by the agent; its contents never reach an LLM.
    """
    from services.vcard_import import import_vcard

    report = import_vcard(request.path, dry_run=not request.apply)
    return {"ok": True, "summary": report.summary(), **report.__dict__}


@app.post("/jobs/contact-learn")
def contact_learn_job(wait: bool = False, _: None = Depends(verify_api_key)):
    """Windmill cron target: update the knowledge of contacts with new messages (no backfill).

    Up to 15 LLM calls, so it runs in the background and returns `{"status": "accepted"}`
    at once (Windmill has a single worker); `?wait=true` runs inline and returns the counts.
    """
    from services.background_jobs import run_in_background, run_inline
    from services.contact_learn_cron import run_contact_learn_batch

    if wait:
        return run_inline("contact-learn", run_contact_learn_batch)
    return run_in_background("contact-learn", run_contact_learn_batch)


@app.post("/run-task")
def run_task(request: TaskRequest, _: None = Depends(verify_api_key)):
    tool_map = {t.name: t for t in AVAILABLE_TOOLS}
    if request.task not in tool_map:
        raise HTTPException(
            status_code=404, detail=f"Tool '{request.task}' not registered."
        )
    try:
        result = tool_map[request.task].invoke(request.params)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
