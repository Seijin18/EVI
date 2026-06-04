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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_state.graph = build_agent_graph(AVAILABLE_TOOLS)
    if os.getenv("DATABASE_URL"):
        try:
            from db import init_db

            init_db()
        except Exception:
            pass
    yield


app = FastAPI(title="EVI — Evolving Virtual Intelligence", lifespan=lifespan)


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
):
    if not app_state.graph:
        raise HTTPException(status_code=500, detail="Agent graph not initialized")

    session_id = request.session_id or x_session_id or app_state.default_session
    _hydrate_memory(session_id)

    user_message = HumanMessage(content=request.message)
    app_state.memory.add(user_message)

    initial_state = {
        "messages": app_state.memory.get_messages(),
        "task_type": "chat",
        "iterations": 0,
        "final_answer": "",
    }

    try:
        result = app_state.graph.invoke(initial_state)
        output_messages = result.get("messages", [])
        final_answer = result.get("final_answer", "")

        if final_answer:
            ai_content = final_answer
        elif output_messages and output_messages[-1].type == "ai":
            ai_content = output_messages[-1].content
        else:
            ai_content = "The agent returned an empty response."

        app_state.memory.clear()
        for msg in output_messages[-16:]:
            app_state.memory.add(msg)

        _persist_turn(session_id, request.message, ai_content)
        return {"response": ai_content, "session_id": session_id}

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
    """Telegram → Windmill or direct → EVI chat graph."""
    if not update.message or "text" not in update.message:
        return {"ok": True, "skipped": "no text"}
    text = update.message["text"]
    chat_id = update.message.get("chat", {}).get("id", "telegram")
    session_id = f"telegram-{chat_id}"
    result = chat(ChatRequest(message=text, session_id=session_id))
    return {"ok": True, "response": result.get("response"), "session_id": session_id}


@app.post("/webhooks/evolution")
def evolution_webhook(
    body: Dict[str, Any],
    _: None = Depends(verify_api_key),
):
    """Evolution API MESSAGES_UPSERT → commitment extraction."""
    from pathlib import Path

    from services.evolution_filter import filter_for_processing
    from services.evolution_parser import parse_evolution_webhook
    from services.whatsapp_processor import WhatsAppProcessor

    log_dir = Path(os.getenv("EVI_LOG_DIR", "/tmp/evi-logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    raw = parse_evolution_webhook(body)
    messages, filter_stats = filter_for_processing(raw, log_dir=log_dir)
    proc = WhatsAppProcessor(log_path=log_dir / "evolution_webhook.jsonl")
    proc.log({"step": "filter", **filter_stats})
    commitments = proc.process_messages(messages)
    proc.flush_log()
    rows = [c.to_golden_row() for c in commitments]
    return {
        "ok": True,
        "received": filter_stats["received"],
        "ingested": len(messages),
        "filter": filter_stats,
        "commitments": rows,
    }


@app.post("/run-task")
def run_task(request: TaskRequest):
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
