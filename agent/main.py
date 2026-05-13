# /home/marshibs/Projects/EVI/agent/main.py
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Dict, Any

from langchain_core.messages import HumanMessage
from graph import build_agent_graph
from memory import BoundedMemory
from tools.file_organizer import organize_inbox
from tools.rag_tool import ingest_university_pdf, query_university_notes
from tools.calendar_tool import schedule_event

# Register all initialized tools
AVAILABLE_TOOLS = [
    organize_inbox,
    ingest_university_pdf,
    query_university_notes,
    schedule_event,
]


class AgentApplicationState:
    graph = None
    memory = BoundedMemory(max_pairs=8)


app_state = AgentApplicationState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup sequence: Compile graph
    app_state.graph = build_agent_graph(AVAILABLE_TOOLS)
    yield
    # Shutdown sequence goes here if needed


app = FastAPI(title="EVI — Evolving Virtual Intelligence", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


class TaskRequest(BaseModel):
    task: str
    params: Dict[str, Any] = {}


@app.get("/")
def root():
    return {"status": "EVI is alive 🟤", "services": ["graph", "tools"]}


@app.get("/tools")
def list_tools():
    return {"tools": [t.name for t in AVAILABLE_TOOLS]}


@app.post("/reset")
def reset_memory():
    app_state.memory.clear()
    return {"status": "Memory wiped."}


@app.post("/chat")
def chat(request: ChatRequest):
    if not app_state.graph:
        raise HTTPException(status_code=500, detail="Agent graph not initialized")

    user_message = HumanMessage(content=request.message)
    app_state.memory.add(user_message)

    initial_state = {
        "messages": app_state.memory.get_messages(),
        "task_type": "chat",
        "iterations": 0,
        "final_answer": "",
    }

    try:
        # Run the graph
        result = app_state.graph.invoke(initial_state)

        output_messages = result.get("messages", [])
        final_answer = result.get("final_answer", "")

        # Determine AI response (use explicitly provided final answer or last AI message)
        if final_answer:
            ai_content = final_answer
        elif output_messages and output_messages[-1].type == "ai":
            ai_content = output_messages[-1].content
        else:
            ai_content = "The agent returned an empty response."

        # Re-sync bounded memory with the updated continuous message chain
        app_state.memory.clear()
        for msg in output_messages[-16:]:  # Bound manually again
            app_state.memory.add(msg)

        return {"response": ai_content}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run-task")
def run_task(request: TaskRequest):
    tool_map = {t.name: t for t in AVAILABLE_TOOLS}

    if request.task not in tool_map:
        raise HTTPException(
            status_code=404, detail=f"Tool '{request.task}' not registered."
        )

    try:
        tool = tool_map[request.task]
        result = tool.invoke(request.params)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
