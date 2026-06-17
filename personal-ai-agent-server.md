# Personal AI Agent Server — Implementation Guide V2

> **Hardware**: Intel i5-7400 · 16GB DDR4 · GTX 1060 3GB · Pop!_OS/Ubuntu
> **Budget**: $0/month · **Stack**: LangGraph + **Windmill** + Evolution API + Ollama + Qdrant + Postgres  
> **Version**: 2.2 — Windmill orchestration; **requirements:** [`openspec/specs/`](openspec/specs/) · **status:** [`Progress.md`](Progress.md) · **backlog:** [`openspec/BACKLOG.md`](openspec/BACKLOG.md)  
> **Legacy note**: Sections below may be outdated; trust OpenSpec specs for as-built behavior.

---

## Current architecture (June 2026 — EVI v3)

| Layer | Component | Role |
|-------|-----------|------|
| Gateway | FastAPI `agent/main.py` + webhooks | Routes Telegram, WhatsApp control, `/chat` |
| Runtime | LangGraph ReAct + `context_assembly` | LLM-first; workspace bootstrap + tool snapshots |
| Workspace | `EVI_WORKSPACE/` | USER.md, AGENTS.md, MEMORY.md, skills |
| Orchestration | **Windmill** | Gmail, Calendar, Tasks (tool hub only) |
| Hot memory | Postgres + `session_tool_snapshots` | Turns + structured tool results |
| Cold memory | `EVI_CONTACT_MEMORY_DIR` | profile.md, timeline.jsonl per JID |
| Messaging ingest | Evolution filter + extract | Webhook pipeline (not chat UX) |
| LLM | Gemini / Ollama fallback | Configurable via `EVI_LLM_PROVIDER` |

**WhatsApp:** ingest → filter → extract → `pending_commitments`; control JIDs → `/chat` grafo.

**Direct handlers:** disabled by default (`EVI_DIRECT_HANDLERS=false`); use LLM + tools.

**Windmill OAuth resources:** `gcal` (Calendar), `gcloud` (Google Tasks API scope), `gmail`.  
**Env:** `WINDMILL_*_RESOURCE`, `WINDMILL_CALENDAR_ID`, `WINDMILL_TOKEN`. See `windmill/README.md`.

**Verify:** `./scripts/evi-test smoke` · `openspec validate --specs`  
**Next changes:** see [`openspec/BACKLOG.md`](openspec/BACKLOG.md).

---

## Framework Decision: LangGraph + n8n + MCP Hybrid

| Framework                   | Pros                                             | Cons                        | Verdict                      |
| --------------------------- | ------------------------------------------------ | --------------------------- | ---------------------------- |
| **LangGraph**         | Full control, ReAct-native, Python-first         | Code-heavy                  | ✅ MCP Client Layer          |
| **n8n (self-hosted)** | Visual workflows, 400+ integrations, Google APIs | Less flexible for reasoning | ✅ Orchestration + webhooks  |
| **MCP Servers**       | Modular, isolated tool execution, type-safe      | Requires config management  | ✅ Tool distribution layer   |
| **Neo4j (Graph DB)**  | Enables reasoning chains, cross-document linking | Adds complexity             | ✅ Knowledge layer (Phase 2) |
| **Ollama**            | Local inference, GPU offload, $0/month           | Limited model variety       | ✅ LLM backbone              |
| **Qdrant**            | Semantic search, low latency, embedded           | Single-threaded by default  | ✅ Vector cache layer        |

**Decision**: LangGraph acts as **MCP Client**. Tools run in isolated MCP Server processes (Filesystem, Memory Router, Calendar). Ollama provides reasoning. n8n handles integrations and webhooks.

---

## RAM Budget (Updated for V2)

```
System + Pop!_OS:           ~2.0 GB
Ollama (Qwen 3B Q4):        ~2.2 GB  (primary reasoning model, full GPU)
Ollama (Llava 7B Q4):       ~0.5 GB  (vision model, loaded on-demand)
Ollama (Whisper small):     ~0.4 GB  (audio transcription, CPU-based)
Qdrant (vector DB):         ~1.0 GB  (semantic cache + embeddings)
Neo4j (knowledge graph):    ~1.5 GB  (GraphRAG, relational facts)
n8n:                        ~0.5 GB  (orchestration + Google APIs)
agent-api (with MCP):       ~2.0 GB  (LangGraph + dependencies)
Postgres (metadata):        ~0.5 GB  (conversation history + facts)
MCP Servers:                ~0.3 GB  (Filesystem, Memory, Router processes)
─────────────────────────────────────
Total Target:              ~10.4 GB ✅ ~5.6GB safe headroom on 16GB
─────────────────────────────────────
Fallback (headless):       ~9.0 GB ✅ (without Whisper + Llava)
```

**Configuration Tips**:

- Ollama VRAM governor: `OLLAMA_MAX_LOADED_MODELS=1` (only 1 model in VRAM at a time)
- Llava unloaded by default: `curl http://localhost:11434/api/generate -d '{"model": "llava", "keep_alive": "5m"}'`
- Whisper on CPU: `device="cpu"`, `compute_type="int8"` (no GPU needed)
- Qdrant cache TTL: 1 hour (reclaim memory from stale vectors)

---

## Phased Rollout Timeline (V2 — 4 Weeks)

```
WEEK 1: Foundation Layer
    ├─ Ollama + Qwen 3B (text reasoning)
    ├─ Docker Compose stack
    ├─ LangGraph basic ReAct loop
    ├─ File organizer (inbox auto-sort)
    └─ DELIVERED: Functional agent that sorts files

WEEK 2: Hybrid Data Layer + GraphRAG Foundation
    ├─ Qdrant (vector semantic cache)
    ├─ Neo4j (knowledge graph for reasoning)
    ├─ RAG pipeline (PDF ingestion + chunking)
    ├─ Graph node extraction (LLM-powered entity linking)
    └─ DELIVERED: Agent can Q&A university notes + reason across concepts

WEEK 3: MCP Orchestration Layer
    ├─ MCP Config (mcp-config.json setup)
    ├─ MCP Servers: Filesystem, Memory Router, Calendar
    ├─ LangGraph as MCP Client (tool dynamic dispatch)
    ├─ Postgres connection for memory persistence
    └─ DELIVERED: Modular tool architecture, multi-layer memory

WEEK 4: Remote UI & Multimodality
    ├─ n8n Webhooks (Google Calendar, Tasks integration)
    ├─ Telegram Bot (remote chat + commands)
    ├─ WhatsApp integration (optional, Twilio)
    ├─ Faster-Whisper (CPU audio transcription)
    ├─ Llava (vision-based document understanding)
    └─ DELIVERED: Full remote multimodal agent (Telegram/WhatsApp)

WEEK 5+: Optional Polish
    ├─ Markdown note auto-generation (journal insights)
    ├─ GitHub Copilot CLI integration (project dev)
    ├─ Redis caching layer (optional perf)
    ├─ Monitoring + Prometheus metrics
    └─ ONGOING: Production hardening
```

---

## Phase 0 — Foundation (Days 1–2)

### 1. Install Ollama & Pull Models

```bash
# Install Ollama (Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull primary models
ollama pull qwen2.5:3b-instruct-q4_K_M    # ~2.2GB VRAM — reasoning (fits GTX 1060 3GB)
ollama pull nomic-embed-text               # ~270MB — embeddings (CPU or unload LLM first)
ollama pull llava:7b-q4_K_M                # vision on-demand; 3GB GPU may need CPU offload
ollama pull whisper-small                  # ~490MB — audio transcription (CPU)

# Set VRAM governor
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KEEP_ALIVE=5m"
EOF

sudo systemctl daemon-reload && sudo systemctl restart ollama

# Verify GPU offload — look for "layers: 32/32"
ollama run qwen2.5:3b-instruct-q4_K_M "Say hello" --verbose
```

### 2. Docker Compose — Full Stack (V2)

```yaml
# ~/Projects/EVI/docker-compose.yml
version: "3.9"

services:
  # Vector Database — Semantic Cache & Embeddings
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes:
      - ./data/qdrant:/qdrant/storage
    environment:
      - QDRANT_TELEMETRY_DISABLED=true
    mem_limit: 1g
    restart: unless-stopped

  # Knowledge Graph — Relational Facts & Reasoning Paths
  neo4j:
    image: neo4j:5-community
    ports: ["7687:7687", "7474:7474"]  # Bolt + HTTP
    environment:
      - NEO4J_AUTH=neo4j/changeme        # ⚠️ Change in .env!
      - NEO4J_PLUGINS='["apoc"]'
      - NEO4J_dbms_memory_heap_max__size=1024m
      - NEO4J_dbms_memory_pagecache_size=512m
    volumes:
      - ./data/neo4j:/data
    mem_limit: 1500m
    restart: unless-stopped

  # Orchestration & Integrations
  n8n:
    image: n8nio/n8n:latest
    ports: ["5678:5678"]
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=changeme    # ⚠️ Change in .env!
      - WEBHOOK_URL=http://localhost:5678
      - N8N_EXECUTIONS_DATA_PRUNE=true
      - N8N_EXECUTIONS_DATA_PRUNE_MAX_COUNT=100
    volumes:
      - ./data/n8n:/home/node/.n8n
    mem_limit: 512m
    restart: unless-stopped

  # Metadata Storage — Conversation History & Facts
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: agentdb
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: agentpass        # ⚠️ Change in .env!
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    mem_limit: 512m
    restart: unless-stopped

  # Agent API — LangGraph as MCP Client
  agent-api:
    build: ./agent
    ports: ["8000:8000"]
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - QDRANT_URL=http://qdrant:6333
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=changeme
      - POSTGRES_URL=postgresql://agent:agentpass@postgres:5432/agentdb
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_WEBHOOK_URL=http://n8n:5678/webhook/telegram
      - MCP_CONFIG_PATH=/app/mcp-config.json
    volumes:
      - ./watched_folders:/watched_folders
      - ./agent/mcp-config.json:/app/mcp-config.json
    mem_limit: 2g
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      - qdrant
      - neo4j
      - postgres
    restart: unless-stopped

networks:
  default:
    name: agent-network
```

```bash
# Boot everything
cd ~/Projects/EVI
cp .env.example .env  # Edit with real secrets
docker compose up -d

# Verify all services running
docker ps

# Monitor RAM usage (target < 12GB)
free -h
docker stats --no-stream
```

### 3. Project Structure (Updated for MCP)

```
Projects/EVI/
├── docker-compose.yml
├── .env                              # Secrets (not versioned)
├── mcp-config.json                   # MCP Server configuration
├── agent/
│   ├── Dockerfile
│   ├── main.py                       # FastAPI + MCP client
│   ├── graph.py                      # LangGraph ReAct loop
│   ├── memory.py                     # 3-layer memory system
│   ├── mcp_client.py                 # MCP interface
│   └── tools/
│       ├── __init__.py
│       ├── file_organizer.py
│       ├── rag_tool.py
│       ├── graph_tool.py             # Neo4j integration
│       ├── note_manager.py           # Auto/manual note generation
│       └── vision_tool.py            # Llava-based vision
├── watched_folders/
│   ├── inbox/                        # Auto-sort trigger
│   ├── inbox_ia/                     # Auto-generated notes output
│   ├── university/
│   ├── code/
│   ├── pdfs/
│   └── unsorted/
├── scripts/
│   ├── watch_and_ingest.sh
│   ├── copilot-dev-runner.sh         # GitHub Copilot CLI integration
│   └── setup-mcp-servers.sh
├── data/                             # Docker volumes
│   ├── qdrant/
│   ├── neo4j/
│   ├── postgres/
│   └── n8n/
└── Progress.md
```

---

## MCP Layer Architecture (NEW — Phase 1+)

### What is MCP?

**Model Context Protocol** = standardized way to distribute tools as isolated processes.

```
OLD (Monolithic):
LangGraph → [file_tool, rag_tool, calendar_tool] (all in one process)
                 ↓ Heavy memory, tight coupling

NEW (MCP-Based):
LangGraph (MCP Client)
    ├─→ MCP Server: Filesystem
    ├─→ MCP Server: Memory Router
    ├─→ MCP Server: Calendar
    └─→ MCP Server: RAG Query
  
Benefits: ✅ Isolated failures, ~300MB per tool, Reloadable, Type-safe
```

### MCP Configuration (`mcp-config.json`)

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "python",
      "args": ["/app/mcp_servers/filesystem_server.py"],
      "env": {"WATCH_DIR": "/watched_folders"},
      "tools": [{"name": "organize_inbox", "description": "Sort files"}]
    },
    "memory_router": {
      "command": "python",
      "args": ["/app/mcp_servers/memory_router_server.py"],
      "tools": [
        {"name": "save_user_fact", "description": "Store user facts"},
        {"name": "recall_user_facts", "description": "Retrieve facts"}
      ]
    },
    "rag_query": {
      "command": "python",
      "args": ["/app/mcp_servers/rag_server.py"],
      "tools": [
        {"name": "query_university_notes", "description": "Search PDFs"},
        {"name": "query_knowledge_graph", "description": "Find reasoning paths"}
      ]
    }
  }
}
```

### LangGraph as MCP Client

```python
# agent/mcp_client.py
import json
import subprocess
from typing import Dict, Any

class MCPClient:
    """Routes tool calls to isolated MCP servers."""
  
    def __init__(self, config_path: str = "mcp-config.json"):
        with open(config_path) as f:
            self.config = json.load(f)
        self.servers = {}
        self._start_all_servers()
  
    def _start_all_servers(self):
        """Start all MCP servers as subprocesses."""
        for name, server_config in self.config["mcpServers"].items():
            cmd = [server_config["command"]] + server_config["args"]
            self.servers[name] = subprocess.Popen(cmd, env={**os.environ, **server_config.get("env", {})})
  
    def call_tool(self, tool_name: str, **kwargs) -> str:
        """Route tool call to appropriate MCP server."""
        # Find which server has this tool
        target_server = None
        for server_name, server_config in self.config["mcpServers"].items():
            tools = [t["name"] for t in server_config.get("tools", [])]
            if tool_name in tools:
                target_server = server_name
                break
      
        if not target_server:
            raise ValueError(f"Tool '{tool_name}' not found")
      
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": kwargs}
        }
      
        process = self.servers[target_server]
        process.stdin.write(json.dumps(request).encode() + b"\n")
        response = process.stdout.readline().decode()
        return json.loads(response).get("result", "")
```

---

## 3-Layer Memory Architecture (NEW)

```python
# agent/memory.py - Tri-layer memory system

class TriLayerMemory:
    """
    SHORT TERM: Last 8 message pairs (LangGraph + Postgres)
    ├─ User queries, reasoning traces, tool calls
  
    MID-TERM: User facts + Knowledge (Neo4j)
    ├─ "prefers morning study sessions"
    ├─ "knows Python, studying OS"
    └─ Relationships: STUDIED, PREFERS, RELATED_TO
  
    LONG-TERM: Semantic recall (Qdrant)
    ├─ "Realized: mutex prevents race conditions"
    ├─ Lesson summaries
    └─ Study patterns
    """
  
    def add_message_short_term(self, role: str, content: str):
        """Store in Postgres + maintain LangGraph state."""
        self.postgres.insert("messages", {
            "timestamp": datetime.now(),
            "role": role,
            "content": content
        })
  
    def save_user_fact(self, fact: str, category: str):
        """Store as Neo4j UserFact node."""
        self.graph.run(
            "MERGE (uf:UserFact {text: $fact, category: $cat})",
            fact=fact, cat=category
        )
  
    def save_insight(self, insight_text: str, tags: list = None):
        """Store as Qdrant embedding for semantic recall."""
        embedding = self.get_embeddings(insight_text)
        self.qdrant.upsert(collection_name="insights", points=[...])
```

---

## Phase 1 — ReAct Agent Core (Days 3–5)

### `agent/graph.py` — LangGraph ReAct Loop (Updated for MCP)

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_ollama import ChatOllama

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    task_type: str
    iterations: int
    final_answer: str
    mcp_tools_available: list

llm = ChatOllama(
    model="qwen2.5:3b-instruct-q4_K_M",
    base_url="http://host.docker.internal:11434",
    temperature=0.1,
    num_ctx=2048,
    num_gpu=-1,
)

SYSTEM_PROMPT = """You are a personal AI assistant with MCP tool support.

MEMORY LAYERS:
1. Short-term: Current conversation (8 pairs)
2. Mid-term: User facts in knowledge graph
3. Long-term: Semantic insights

Reasoning: Thought → Action → Observation → Final Answer"""

def agent_node(state: AgentState):
    if state["iterations"] > 10:
        return {**state, "final_answer": "Max iterations."}
  
    llm_with_tools = llm.bind_tools(state["mcp_tools_available"])
    response = llm_with_tools.invoke([SystemMessage(...)] + state["messages"])
    return {**state, "messages": [response], "iterations": state["iterations"] + 1}

def should_continue(state: AgentState) -> str:
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return END
```

### `agent/tools/file_organizer.py`

```python
from langchain_core.tools import tool
from pathlib import Path
import shutil, hashlib

SORT_RULES = {
    "university": {
        "extensions": [".pdf", ".pptx", ".docx"],
        "keywords": ["lecture", "notes", "assignment"],
        "dest": "/watched_folders/university"
    },
    "code": {
        "extensions": [".py", ".js", ".ts"],
        "keywords": ["project", "homework"],
        "dest": "/watched_folders/code"
    }
}

@tool
def organize_inbox(confirm: bool = False) -> str:
    """Sort files from inbox into categorized folders."""
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
            shutil.move(str(file), str(dest / file.name))
  
    return "\n".join(results) if results else "Inbox is empty."
```

---

## Phase 2 — Hybrid Data Layer: Qdrant + Neo4j (Days 6–10)

### `agent/tools/rag_tool.py` — Semantic Search

```python
from langchain_community.document_loaders import PyMuPDFLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore

EMBED_MODEL = "nomic-embed-text"

embeddings = OllamaEmbeddings(
    model=EMBED_MODEL,
    base_url="http://host.docker.internal:11434"
)

@tool
def ingest_university_folder(folder_path: str = "/watched_folders/university") -> str:
    """Ingest all PDFs into Qdrant."""
    loader = DirectoryLoader(folder_path, glob="**/*.pdf", loader_cls=PyMuPDFLoader)
    docs = loader.load()
  
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=512, chunk_overlap=64
    )
    chunks = splitter.split_documents(docs)
  
    store = QdrantVectorStore(...)
    for i in range(0, len(chunks), 50):
        store.add_documents(chunks[i:i+50])
  
    return f"Ingested {len(docs)} → {len(chunks)} chunks."

@tool
def query_university_notes(question: str, top_k: int = 4) -> str:
    """Search notes semantically."""
    store = QdrantVectorStore(...)
    results = store.similarity_search_with_score(question, k=top_k)
  
    if not results:
        return "No relevant notes."
  
    formatted = []
    for doc, score in results:
        formatted.append(f"[{score:.2f}] {doc.page_content[:200]}")
  
    return "\n\n".join(formatted)
```

### `agent/tools/graph_tool.py` — Neo4j Knowledge Graph

```python
from neo4j import GraphDatabase

class KnowledgeGraphManager:
    def __init__(self):
        self.driver = GraphDatabase.driver("bolt://localhost:7687", 
                                          auth=("neo4j", "changeme"))
  
    def add_entity(self, entity_type: str, name: str):
        with self.driver.session() as session:
            session.run(f"MERGE (n:{entity_type} {{name: $name}})", name=name)
  
    def query_path(self, start: str, end: str, max_depth: int = 3) -> list:
        """Find reasoning path between concepts."""
        with self.driver.session() as session:
            result = session.run(
                "MATCH path = shortestPath((a {name: $start})-[*...$depth]->(b {name: $end})) "
                "RETURN [node in nodes(path) | node.name]",
                start=start, end=end, depth=max_depth
            )
            paths = [record[0] for record in result if record[0]]
            return paths[0] if paths else []

kg_manager = KnowledgeGraphManager()

@tool
def query_knowledge_graph(start: str, end: str) -> str:
    """Find reasoning path."""
    path = kg_manager.query_path(start, end)
    if path:
        return f"Path: {' → '.join(path)}"
    return f"No path between '{start}' and '{end}'."
```

---

## Phase 3 — MCP Orchestration (Days 11–14)

### MCP Servers Setup

```bash
mkdir -p ~/Projects/EVI/agent/mcp_servers
# Create: filesystem_server.py, memory_router_server.py, rag_server.py
bash scripts/setup-mcp-servers.sh
```

### Windmill integration scripts (replaces n8n webhooks)

| Script | Agent tool / webhook | Env |
|--------|----------------------|-----|
| `f/integrations/schedule_event` | `schedule_event` | `WINDMILL_WEBHOOK_CALENDAR` |
| `f/integrations/create_task` | `create_task` | `WINDMILL_WEBHOOK_TASKS` |
| `f/integrations/summarize_inbox` | `summarize_inbox` | `WINDMILL_WEBHOOK_EMAIL` |
| `f/integrations/telegram_to_evi` | `POST /webhooks/telegram` | `WINDMILL_WEBHOOK_TELEGRAM` |

Sync: `cd windmill && wmill sync push`. HTTP triggers need `?token=` or `WINDMILL_TOKEN` Bearer.

---

## Phase 4 — Remote UI & Multimodality (Days 15–20)

### Audio with Faster-Whisper (CPU-Optimized)

```bash
# Add to agent/Dockerfile
RUN pip install --no-cache-dir \
    faster-whisper==0.10.0 \
    librosa==0.10.0 \
    soundfile==0.12.1
```

### `agent/tools/audio_tool.py`

```python
from faster_whisper import WhisperModel

# Runs FULLY on CPU
whisper_model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8"
)

@tool
def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio on CPU."""
    segments, info = whisper_model.transcribe(
        audio_path, language="en", beam_size=5
    )
  
    formatted = f"**Duration**: {info.duration:.1f}s\n\n"
    for segment in segments:
        formatted += f"[{int(segment.start)}s] {segment.text}\n"
  
    return formatted
```

### Vision with Llava (On-Demand)

```python
# agent/tools/vision_tool.py
from langchain_ollama import ChatOllama

llm_vision = ChatOllama(
    model="llava:7b-q4_K_M",
    base_url="http://host.docker.internal:11434",
    num_gpu=99
)

@tool
def analyze_document_image(image_path: str) -> str:
    """Analyze images using Llava."""
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()
  
    response = llm_vision.invoke([
        HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
            {"type": "text", "text": "Describe this image and extract text."}
        ])
    ])
  
    # Unload Llava to free VRAM
    subprocess.run([
        "curl", "-X", "POST", "http://localhost:11434/api/generate",
        "-d", '{"model": "llava", "keep_alive": "0"}'
    ])
  
    return response.content
```

### Telegram Bot

```bash
# 1. Create bot with @BotFather
# 2. Set in .env:
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_WEBHOOK_URL=http://n8n:5678/webhook/telegram
```

### Auto-Save Notes System (NEW)

```python
# agent/tools/note_manager.py
from datetime import datetime
from pathlib import Path

NOTES_DIR = Path("/watched_folders/inbox_ia")

class NoteManager:
    @staticmethod
    def create_frontmatter(title: str, tags: list, category: str) -> str:
        return f"""---
title: "{title}"
date: {datetime.now().isoformat()}
tags: {json.dumps(tags)}
category: {category}
type: "user-insight"
---

"""
  
    @staticmethod
    def auto_generate_note(conversation_history: list, llm) -> str:
        """AUTO: Extract insights from conversation end."""
        conv_text = "\n".join([f"[{msg['role']}]: {msg['content']}" 
                               for msg in conversation_history[-10:]])
      
        extraction_prompt = f"""
        Extract:
        1. Key learnings (2-3 bullets)
        2. Questions that emerged
        3. Action items
        4. Related concepts (tags)
      
        Conversation:
        {conv_text}
        """
      
        extracted = llm.invoke(extraction_prompt)
      
        # Determine category
        category = "conversation-insight"
        if "homework" in conv_text.lower():
            category = "homework"
      
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_auto_insight.md"
      
        content = NoteManager.create_frontmatter(
            title=f"Insight {datetime.now().strftime('%Y-%m-%d')}",
            tags=["auto-generated", category],
            category=category
        )
        content += f"## Auto-Generated Insight\n\n{extracted}"
      
        (NOTES_DIR / filename).write_text(content)
        return f"✅ Note: {filename}"
  
    @staticmethod
    def manual_save_note(title: str, content: str, tags: list = None, category: str = "general") -> str:
        """MANUAL: User command to save structured notes."""
        frontmatter = NoteManager.create_frontmatter(title, tags or [], category)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{title.lower().replace(' ', '_')}.md"
      
        (NOTES_DIR / filename).write_text(frontmatter + content)
        return f"✅ Note saved: {filename}"

note_manager = NoteManager()

@tool
def save_note_manual(title: str, content: str, tags: list = None, category: str = "general") -> str:
    """MANUAL: Save as structured Markdown."""
    return note_manager.manual_save_note(title, content, tags, category)

@tool
def trigger_auto_notes(conversation_history: list) -> str:
    """AUTO: Triggered at conversation end."""
    return note_manager.auto_generate_note(conversation_history, llm)
```

---

## GitHub Copilot CLI Integration (NEW)

GitHub Copilot CLI for heavy dev tasks; keep local LLM for runtime reasoning.

### Installation

```bash
npm install -g @github/copilot-cli
copilot auth
copilot --version
```

### Use Cases

```bash
# 1. EXPLAIN errors
copilot explain "docker compose up failed with OOM"

# 2. SCAFFOLD tests
copilot scaffold "Generate pytest for agent/tools/file_organizer.py"

# 3. BUILD new tools
copilot build "Create MCP server for email integration"

# 4. DEBUG issues
copilot diagnose "LangGraph timeout after 10 iterations"

# 5. OPTIMIZE performance
copilot optimize "Qdrant queries slow with 50k embeddings"

# 6. REFACTOR code
copilot refactor "Consolidate memory.py layers"
```

### Integration Script

```bash
#!/bin/bash
# scripts/copilot-dev-runner.sh

TASK=$1

case $TASK in
  "scaffold-tool")
    TOOL_NAME=$2
    copilot build "Create MCP tool for $TOOL_NAME with error handling"
    ;;
  "test-coverage")
    copilot scaffold "Generate pytest for agent/graph.py"
    ;;
  "debug-oom")
    docker stats --no-stream | copilot explain "Why exceed memory?"
    ;;
  "optimize-rag")
    copilot optimize "10k PDFs → 5s queries. Optimizations?"
    ;;
  "document-api")
    copilot scaffold "Generate OpenAPI docs for agent-api:8000"
    ;;
  *)
    echo "Usage: $0 {scaffold-tool|test-coverage|debug-oom|optimize-rag|document-api}"
    ;;
esac
```

### Usage

```bash
# Generate tests
bash scripts/copilot-dev-runner.sh test-coverage
# → Generates pytest with 20+ test cases

# Debug RAM issues
bash scripts/copilot-dev-runner.sh debug-oom
# → Analyzes docker stats + recommends

# LOCAL LLM stays for:
# - Runtime agent reasoning
# - RAG queries on private data
# - Real-time inference
```

---

## Complete Setup Checklist

### Week 1: Foundation

- [ ] Install Ollama + models (Qwen, embed, Llava, Whisper)
- [ ] Docker Compose up
- [ ] LangGraph ReAct loop working
- [ ] File organizer tested
- [ ] < 12GB RAM usage

### Week 2: Data Layer

- [ ] RAG ingestion complete
- [ ] Qdrant populated
- [ ] Neo4j ingesting entities
- [ ] Query benchmarks

### Week 3: MCP + Memory

- [ ] MCP servers started
- [ ] mcp-config.json validated
- [ ] 3-layer memory tested
- [ ] Postgres history working

### Week 4: Remote + Multimodal

- [ ] Telegram bot responding
- [ ] Faster-Whisper transcribing (CPU)
- [ ] Llava analyzing images
- [ ] Auto-notes saving

---

## Troubleshooting

| Problem                     | Solution                                         |
| --------------------------- | ------------------------------------------------ |
| "CUDA out of memory"        | Reduce `num_gpu` or use `device="cpu"`       |
| "Neo4j won't start"         | Check `docker logs` — auth/memory limit       |
| "MCP tool not found"        | Validate `mcp-config.json` schema              |
| "Qdrant slow"               | Add vector index                                 |
| "Telegram webhook failing"  | Verify webhook URL + bot token                   |
| "Auto-notes not generating" | Check history format, LLM response, dir writable |

---

## Architecture Summary

```
┌─────────────────────────────┐
│ Telegram / WhatsApp UI      │
└────────────┬────────────────┘
             │
┌────────────▼────────────────┐
│ n8n Orchestration           │
└────────────┬────────────────┘
             │
┌────────────▼────────────────────────┐
│ LangGraph ReAct (MCP Client)        │
│ • Reasoning (Qwen 3B)               │
│ • Memory (3-layer)                  │
│ • Tool dispatch                     │
└─┬──────────────┬──────────────┬─────┘
  │              │              │
  ├─ MCP:Files   ├─ MCP:Memory  └─ MCP:RAG
  │              │
  ├─ Qdrant      ├─ Neo4j ─── Postgres
  │ Embeddings   │ Graph      History
  └──────────────┴─────────────────────
              ▲
              │ Ollama
              │ (Qwen, Llava, Whisper)
              │
        GPU (GTX 1060) + CPU (i5)
```

---

## Next Steps

1. ✅ **Week 1**: Foundation (ReAct + file organizer)
2. ✅ **Week 2**: RAG + knowledge graph
3. ✅ **Week 3**: MCP servers + memory
4. ✅ **Week 4**: Telegram + Whisper + Llava
5. 🔄 **Ongoing**: Polish + GitHub Copilot CLI

**EVI Status**: ✅ Phases 1–4 Designed · 🚀 Ready for phased rollout
