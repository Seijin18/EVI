# /home/marshibs/Projects/EVI/agent/main.py
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from auth import verify_api_key
from graph import build_agent_graph
from memory import BoundedMemory
from tools.note_manager import build_auto_insight, save_note_manual
from tools.registry import get_all_tools

AVAILABLE_TOOLS = get_all_tools()


class AgentApplicationState:
    graph = None
    memory = BoundedMemory(max_pairs=8)
    default_session = "default"


app_state = AgentApplicationState()


def _persist_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    if not os.getenv("DATABASE_URL"):
        return
    try:
        from db import save_message

        save_message(session_id, "user", user_text)
        save_message(session_id, "assistant", assistant_text)
    except Exception:
        pass


def _hydrate_memory(session_id: str) -> None:
    if not os.getenv("DATABASE_URL"):
        return
    try:
        from db import load_recent_messages

        rows = load_recent_messages(session_id, limit=16)
        app_state.memory.clear()
        for row in rows:
            if row["role"] == "user":
                app_state.memory.add(HumanMessage(content=row["content"]))
            else:
                app_state.memory.add(AIMessage(content=row["content"]))
    except Exception:
        pass


def _reset_session(_session_id: str) -> None:
    app_state.memory.clear()


def _compact_session(session_id: str) -> None:
    from services.memory_flush import maybe_flush_before_compaction
    from llm import extract_llm_text

    msgs = app_state.memory.get_messages()
    last_user = ""
    last_ai = ""
    for m in reversed(msgs):
        if getattr(m, "type", None) == "ai" and not last_ai:
            last_ai = extract_llm_text(getattr(m, "content", ""))
        if getattr(m, "type", None) == "human" and not last_user:
            last_user = str(getattr(m, "content", ""))
        if last_user and last_ai:
            break
    maybe_flush_before_compaction(
        session_id=session_id,
        messages=msgs,
        user_text=last_user,
        assistant_text=last_ai,
    )
    kept = msgs[-4:]
    app_state.memory.clear()
    for msg in kept:
        app_state.memory.add(msg)


def _telegram_invoke_chat(message: str, session_id: str) -> Dict[str, Any]:
    return chat(ChatRequest(message=message, session_id=session_id))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_state.graph = build_agent_graph(AVAILABLE_TOOLS)
    if os.getenv("DATABASE_URL"):
        try:
            from db import init_db

            init_db()
        except Exception:
            pass
    if os.getenv("TELEGRAM_MODE", "").strip().lower() == "polling":
        from services.telegram_poller import start_poller

        start_poller(
            _telegram_invoke_chat,
            reset_session=_reset_session,
            compact_session=_compact_session,
        )
    try:
        from pathlib import Path
        from services.log_retention import prune_logs

        prune_logs(Path(os.getenv("EVI_LOG_DIR", "/logs")))
    except Exception:
        pass
    gmail_res = os.getenv("WINDMILL_GMAIL_RESOURCE", "")
    if gmail_res:
        print(f"EVI: WINDMILL_GMAIL_RESOURCE={gmail_res}", flush=True)
    yield


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
def metrics():
    from services.metrics import metrics_response

    return metrics_response()


@app.get("/tools")
def list_tools():
    return {"tools": [t.name for t in AVAILABLE_TOOLS]}


@app.post("/reset")
def reset_memory():
    app_state.memory.clear()
    return {"status": "Memory wiped."}


@app.post("/chat")
def chat(
    request: ChatRequest,
    x_session_id: Optional[str] = Header(default=None),
    _: None = Depends(verify_api_key),
):
    if not app_state.graph:
        raise HTTPException(status_code=500, detail="Agent graph not initialized")

    session_id = request.session_id or x_session_id or app_state.default_session

    from services.session_lane import session_lane

    with session_lane(session_id):
        return _chat_impl(request, session_id)


def _chat_impl(request: ChatRequest, session_id: str) -> Dict[str, Any]:
    _hydrate_memory(session_id)

    from services.context_assembly import build_context
    from services.memory_flush import maybe_flush_before_compaction
    from services.session_context import persist_tool_snapshots, summarize_tool_calls

    extra_context = build_context(session_id, request.message)

    def _on_trim() -> None:
        msgs = app_state.memory.get_messages()
        last_user = ""
        last_ai = ""
        for m in reversed(msgs):
            if getattr(m, "type", None) == "ai" and not last_ai:
                from llm import extract_llm_text

                last_ai = extract_llm_text(getattr(m, "content", ""))
            if getattr(m, "type", None) == "human" and not last_user:
                last_user = str(getattr(m, "content", ""))
            if last_user and last_ai:
                break
        maybe_flush_before_compaction(
            session_id=session_id,
            messages=msgs,
            user_text=last_user,
            assistant_text=last_ai,
        )

    app_state.memory.set_on_trim(_on_trim)

    user_message = HumanMessage(content=request.message)
    app_state.memory.add(user_message)

    initial_state = {
        "messages": app_state.memory.get_messages(),
        "task_type": "chat",
        "iterations": 0,
        "final_answer": "",
        "extra_context": extra_context,
    }

    try:
        result = app_state.graph.invoke(initial_state)
        output_messages = result.get("messages", [])
        final_answer = result.get("final_answer", "")

        from llm import extract_llm_text

        if final_answer:
            ai_content = extract_llm_text(final_answer)
        elif output_messages and output_messages[-1].type == "ai":
            ai_content = extract_llm_text(output_messages[-1].content)
        else:
            ai_content = "The agent returned an empty response."

        tool_audit = summarize_tool_calls(output_messages)
        persist_tool_snapshots(session_id, output_messages)

        app_state.memory.clear()
        for msg in output_messages[-16:]:
            app_state.memory.add(msg)

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
def save_note(request: NoteRequest):
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
def generate_insight(request: InsightRequest):
    session_id = request.session_id or app_state.default_session
    turns = []
    for msg in app_state.memory.get_messages():
        turns.append(
            {"role": "user" if msg.type == "human" else "assistant", "content": msg.content}
        )
    if not turns and os.getenv("DATABASE_URL"):
        try:
            from db import load_recent_messages

            for row in load_recent_messages(session_id, limit=8):
                turns.append({"role": row["role"], "content": row["content"]})
        except Exception:
            pass
    try:
        path = build_auto_insight(turns, session_id=session_id)
        return {"path": path, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhooks/telegram")
def telegram_webhook(
    update: TelegramUpdate,
    _: None = Depends(verify_api_key),
):
    """Telegram webhook → EVI chat (use TELEGRAM_MODE=polling to skip tunnel)."""
    from services.telegram_handler import process_telegram_update

    payload = update.model_dump() if hasattr(update, "model_dump") else {"message": update.message}
    return process_telegram_update(
        payload,
        _telegram_invoke_chat,
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
    raw = parse_evolution_webhook(body)
    from services.evolution_client import is_evi_bot_message
    from services.whatsapp_control import (
        parse_control_jids,
        process_whatsapp_control_message,
    )

    control_jids = parse_control_jids()
    control_results: list[dict] = []
    ingest_raw = []
    for msg in raw:
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
                invoke_chat=_telegram_invoke_chat,
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
        else:
            ingest_raw.append(msg)

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
        except Exception:
            pass
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

        init_db()
        msg_by_id = {m.id: m for m in messages}
        for c in commitments:
            raw = msg_by_id.get(c.source_id)
            raw_text = raw.text if raw else ""
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
            )
            if row_id:
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
                except Exception:
                    pass
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
                except Exception:
                    pass
                try:
                    from services.commitment_capture_notify import (
                        notify_commitment_captured,
                    )

                    notify_commitment_captured(row_id, c.title, c.type)
                except Exception:
                    pass
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
    except Exception:
        pass

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


@app.post("/jobs/contact-learn")
def contact_learn_job(_: None = Depends(verify_api_key)):
    """Windmill cron target: re-synthesize active contacts (no Evolution backfill)."""
    from services.contact_learn_cron import run_contact_learn_batch

    return run_contact_learn_batch()


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
