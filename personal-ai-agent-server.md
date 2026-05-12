# Personal AI Agent Server — Implementation Plan

> **Hardware**: Intel i5 6th Gen · 16GB DDR4 · GTX 1060 6GB · Pop!_OS/Ubuntu  
> **Budget**: $0/month · **Stack**: LangGraph + n8n + Ollama + Qdrant

---

## Framework Decision: LangGraph + n8n Hybrid

| Framework | Pros | Cons | Verdict |
|---|---|---|---|
| **LangGraph** | Full control, ReAct-native, Python-first | Code-heavy | ✅ Core agent logic |
| **n8n (self-hosted)** | Visual workflows, 400+ integrations, Google APIs built-in | Less flexible for complex reasoning | ✅ Orchestration + integrations |
| **CrewAI** | Easy multi-agent | Heavy RAM usage, opinionated | ❌ Too heavy for 16GB |
| **AutoGen** | Microsoft-backed, flexible | Complex setup, high overhead | ❌ Overkill for solo use |

**Decision:** LangGraph handles ReAct agent loops; n8n handles scheduling, Google APIs, and triggers. They communicate via a local REST API.

---

## RAM Budget

```
System + Pop!_OS:        ~2.0 GB
Ollama (model loaded):   ~4.5 GB  (Qwen 7B Q4)
Qdrant:                  ~1.0 GB
n8n:                     ~0.5 GB
agent-api:               ~2.0 GB
Postgres:                ~0.5 GB
─────────────────────────────────
Total:                  ~10.5 GB  ✅ 5.5GB headroom
```

---

## Phased Rollout Timeline

```
Week 1:  Phase 0+1 — Ollama + Docker + ReAct loop + file organizer running
Week 2:  Phase 2   — RAG ingestion working, can Q&A your lecture PDFs
Week 3:  Phase 3   — n8n live, Google Calendar connected
Week 4:  Polish    — Tailscale remote access, cron jobs, monitoring dashboard
```

---

## Phase 0 — Foundation (Day 1–2)

### 1. Install Ollama & Pull Models

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull primary models (fits in 6GB VRAM with 4-bit quantization)
ollama pull qwen2.5:7b-instruct-q4_K_M    # ~4.1GB VRAM — primary reasoning
ollama pull nomic-embed-text               # ~270MB — embeddings for RAG

# Verify GPU offload — look for "gpu layers: 32/32"
ollama run qwen2.5:7b-instruct-q4_K_M "Say hello" --verbose
```

### 2. Docker Compose — Full Stack

```yaml
# ~/agent-server/docker-compose.yml
version: "3.9"

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes:
      - ./data/qdrant:/qdrant/storage
    mem_limit: 1g

  n8n:
    image: n8nio/n8n:latest
    ports: ["5678:5678"]
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=changeme
      - WEBHOOK_URL=http://localhost:5678
    volumes:
      - ./data/n8n:/home/node/.n8n
    mem_limit: 512m

  agent-api:
    build: ./agent
    ports: ["8000:8000"]
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - QDRANT_URL=http://qdrant:6333
    volumes:
      - ./watched_folders:/watched_folders
    mem_limit: 2g
    extra_hosts:
      - "host.docker.internal:host-gateway"

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: agentdb
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: agentpass
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    mem_limit: 512m
```

```bash
# Boot everything
cd ~/agent-server && docker compose up -d

# Check RAM usage (target: < 5GB used)
free -h && docker stats --no-stream
```

### 3. Project Structure

```
agent-server/
├── docker-compose.yml
├── agent/
│   ├── Dockerfile
│   ├── main.py             # FastAPI entrypoint
│   ├── graph.py            # LangGraph ReAct loop
│   ├── tools/
│   │   ├── file_organizer.py
│   │   ├── rag_tool.py
│   │   └── calendar_tool.py
│   └── memory.py           # Conversation + episodic memory
├── watched_folders/
│   ├── inbox/              # Drop files here → agent auto-sorts
│   ├── university/
│   └── code/
└── data/                   # Docker volumes
```

---

## Phase 1 — ReAct Agent Core (Day 3–5)

### `agent/graph.py` — The ReAct Loop

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    task_type: str          # "file_org" | "rag_query" | "schedule"
    iterations: int         # Guard against infinite loops
    final_answer: str

llm = ChatOllama(
    model="qwen2.5:7b-instruct-q4_K_M",
    base_url="http://host.docker.internal:11434",
    temperature=0.1,        # Low temp for tool-calling accuracy
    num_ctx=4096,           # Context window — balance quality vs RAM
    num_gpu=99,             # Offload all layers to VRAM
)

SYSTEM_PROMPT = """You are a personal AI assistant running on a local server.
You have tools to organize files, query university notes, and manage schedules.
Think step by step. Use tools when needed. Be concise — you run on limited hardware.

Available tools: {tool_names}
Format: Thought → Action → Observation → ... → Final Answer"""

def agent_node(state: AgentState) -> AgentState:
    """Core reasoning node — decides next action."""
    if state["iterations"] > 10:          # Safety: prevent infinite ReAct loops
        return {**state, "final_answer": "Max iterations reached.",
                "messages": state["messages"]}

    llm_with_tools = llm.bind_tools(tools)
    system = SystemMessage(content=SYSTEM_PROMPT.format(
        tool_names=[t.name for t in tools]
    ))

    response = llm_with_tools.invoke([system] + state["messages"])
    return {
        **state,
        "messages": [response],
        "iterations": state["iterations"] + 1
    }

def should_continue(state: AgentState) -> str:
    """Router: tool call → tools node, else → end."""
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return END

def build_agent_graph(tool_list: list):
    global tools
    tools = tool_list

    tool_node = ToolNode(tools)
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")

    graph.add_conditional_edges("agent", should_continue,
                                {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")    # Always loop back after tool use

    return graph.compile()
```

### `agent/tools/file_organizer.py`

```python
from langchain_core.tools import tool
from pathlib import Path
import shutil, hashlib

SORT_RULES = {
    "university": {
        "extensions": [".pdf", ".pptx", ".docx"],
        "keywords":   ["lecture", "notes", "assignment", "exam", "lab"],
        "dest":       "/watched_folders/university"
    },
    "code": {
        "extensions": [".py", ".js", ".ts", ".c", ".cpp", ".ipynb"],
        "keywords":   ["project", "homework", "solution"],
        "dest":       "/watched_folders/code"
    },
    "pdfs_general": {
        "extensions": [".pdf"],
        "keywords":   [],
        "dest":       "/watched_folders/pdfs"
    }
}

@tool
def organize_inbox(confirm: bool = False) -> str:
    """
    Scans /watched_folders/inbox and sorts files into categorized folders.
    Set confirm=True to actually move files (dry-run by default).
    """
    inbox = Path("/watched_folders/inbox")
    results = []

    for file in inbox.iterdir():
        if file.is_dir():
            continue

        dest_folder = _classify_file(file)
        action = f"{'MOVE' if confirm else 'PLAN'}: {file.name} → {dest_folder}"
        results.append(action)

        if confirm:
            dest = Path(dest_folder)
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / file.name
            if target.exists():
                h = hashlib.md5(file.read_bytes()).hexdigest()[:6]
                target = dest / f"{file.stem}_{h}{file.suffix}"
            shutil.move(str(file), str(target))

    return "\n".join(results) if results else "Inbox is empty."

def _classify_file(file: Path) -> str:
    name_lower = file.name.lower()
    ext = file.suffix.lower()

    for category, rules in SORT_RULES.items():
        ext_match     = ext in rules["extensions"]
        keyword_match = any(kw in name_lower for kw in rules["keywords"])
        if ext_match and (keyword_match or not rules["keywords"]):
            return rules["dest"]

    return "/watched_folders/unsorted"
```

---

## Phase 2 — RAG System for University Notes (Day 6–10)

### `agent/tools/rag_tool.py`

```python
from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_core.tools import tool
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import os

QDRANT_URL  = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION  = "university_notes"
EMBED_MODEL = "nomic-embed-text"   # Runs on CPU — preserves VRAM for LLM

embeddings = OllamaEmbeddings(
    model=EMBED_MODEL,
    base_url="http://host.docker.internal:11434"
)

def get_vector_store():
    client = QdrantClient(url=QDRANT_URL)
    if COLLECTION not in [c.name for c in client.get_collections().collections]:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE)
        )
    return QdrantVectorStore(client=client, collection_name=COLLECTION,
                             embedding=embeddings)

@tool
def ingest_university_folder(folder_path: str = "/watched_folders/university") -> str:
    """
    Ingests all PDFs and documents in a folder into the RAG vector store.
    Run this after adding new lecture notes or assignments.
    """
    loader = DirectoryLoader(folder_path, glob="**/*.pdf",
                             loader_cls=PyPDFLoader, show_progress=True)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,       # Tuned for 768-dim embeddings
        chunk_overlap=64,     # Preserve context across chunks
        separators=["\n\n", "\n", ". ", " "]
    )
    chunks = splitter.split_documents(docs)

    store = get_vector_store()
    BATCH = 50
    for i in range(0, len(chunks), BATCH):
        store.add_documents(chunks[i:i+BATCH])

    return f"Ingested {len(docs)} documents → {len(chunks)} chunks into Qdrant."

@tool
def query_university_notes(question: str, top_k: int = 4) -> str:
    """
    Searches your university notes and returns relevant context.
    Use to answer questions about lecture content, assignments, or topics.
    """
    store = get_vector_store()
    results = store.similarity_search_with_score(question, k=top_k)

    if not results:
        return "No relevant notes found. Have you run ingest_university_folder yet?"

    formatted = []
    for doc, score in results:
        source = doc.metadata.get("source", "unknown")
        page   = doc.metadata.get("page", "?")
        formatted.append(
            f"[Score: {score:.2f} | {Path(source).name} p.{page}]\n{doc.page_content}"
        )

    return "\n\n---\n\n".join(formatted)
```

### Auto-Ingest Watcher Script

```bash
# ~/agent-server/scripts/watch_and_ingest.sh
#!/bin/bash
WATCH_DIR="/home/$USER/agent-server/watched_folders/university"
API_URL="http://localhost:8000/run-task"

inotifywait -m -r -e close_write --format '%w%f' "$WATCH_DIR" | while read FILE; do
    echo "[$(date)] New file detected: $FILE"
    curl -s -X POST "$API_URL" \
      -H "Content-Type: application/json" \
      -d "{\"task\": \"ingest_university_folder\", \"params\": {\"folder_path\": \"$WATCH_DIR\"}}"
done

# Install dependency: sudo apt install inotify-tools
# Run as service:    systemctl --user enable agent-watcher
```

---

## Phase 3 — Google Calendar via n8n (Day 11–14)

### n8n Workflow Architecture

```
Trigger: Webhook (POST /agent-task)
    ↓
Function Node: Parse task type
    ↓
Switch: route by task_type
    ├─ "schedule_event"  → Google Calendar node → Create Event
    ├─ "list_events"     → Google Calendar node → Get Events → Format
    └─ "agent_query"     → HTTP Request → agent-api:8000 → Return response
```

### `agent/tools/calendar_tool.py`

```python
# The agent calls n8n, which holds OAuth tokens — zero secrets in Python
from langchain_core.tools import tool
import httpx, os

N8N_WEBHOOK = os.getenv("N8N_WEBHOOK_URL", "http://n8n:5678/webhook/calendar")

@tool
def create_calendar_event(
    title: str,
    date: str,               # ISO format: "2026-05-15"
    time: str,               # "14:00"
    duration_minutes: int = 60,
    description: str = ""
) -> str:
    """Creates a Google Calendar event for study sessions, deadlines, or appointments."""
    payload = {
        "action": "create",
        "title": title,
        "date": date,
        "time": time,
        "duration": duration_minutes,
        "description": description
    }
    response = httpx.post(N8N_WEBHOOK, json=payload, timeout=15)
    return response.json().get("message", "Event created successfully.")

@tool
def list_upcoming_events(days_ahead: int = 7) -> str:
    """Lists your Google Calendar events for the next N days."""
    response = httpx.post(N8N_WEBHOOK,
                          json={"action": "list", "days": days_ahead},
                          timeout=15)
    events = response.json().get("events", [])
    if not events:
        return "No upcoming events found."
    return "\n".join([f"• {e['date']} {e['time']} — {e['title']}" for e in events])
```

---

## Phase 4 — GitHub Copilot Cost Avoidance

### Use Copilot For vs Local LLM For

| Use Copilot For (unlimited "Auto") | Use Local LLM For |
|---|---|
| Writing boilerplate tool wrappers | All runtime agent reasoning |
| LangGraph node scaffolding | RAG query answering |
| Docker / bash script generation | Document summarization |
| Unit tests for tools | Calendar parsing |
| Debugging tracebacks in VS Code | Anything with private data |

### VS Code Settings

```jsonc
// .vscode/settings.json
{
  "github.copilot.editor.enableAutoCompletions": true,
  "github.copilot.chat.localeOverride": "en",
  "github.copilot.chat.useProjectTemplates": true
}
```

### Effective Copilot Chat Prompts

```
"Generate a LangGraph tool node for [task] following the pattern in graph.py"
"Write a Dockerfile for a FastAPI app using langchain-ollama with no network calls"
"Create pytest tests for the organize_inbox tool with mock filesystem"
"Refactor this agent node to add exponential backoff on Ollama timeouts"
```

---

## Performance Hardening

### Ollama VRAM Governor

```ini
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_FLASH_ATTENTION=1"    # GTX 1060 supported — ~15% speedup
```

```bash
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

### Bounded Memory (Prevent Context Bloat)

```python
# agent/memory.py
from collections import deque
from langchain_core.messages import BaseMessage

class BoundedMemory:
    """Keeps only the last N message pairs to cap RAM usage."""

    def __init__(self, max_pairs: int = 8):
        self.buffer: deque = deque(maxlen=max_pairs * 2)

    def add(self, message: BaseMessage):
        self.buffer.append(message)

    def get_messages(self) -> list:
        return list(self.buffer)

    def clear(self):
        self.buffer.clear()
```

### Swap Safety Net

```bash
# Prevent OOM kills during ingestion
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile && sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Only use swap as last resort
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

---

## Quick Start (All Phases Complete)

```bash
# Boot the full stack
cd ~/agent-server && docker compose up -d && \
  bash scripts/watch_and_ingest.sh &

# Chat with your agent
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Summarize my Operating Systems notes and schedule a study session tomorrow at 3pm"}'
```

> **Expected performance**: GTX 1060 with Q4 quantization → ~8–12 tokens/sec on Qwen 7B.  
> Full stack stays within $0/month budget with Copilot handling all scaffolding.
