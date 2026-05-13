# Personal AI Agent Server — Implementation Progress

> **Start Date**: May 12, 2026
> **Hardware**: Intel i5 6th Gen · 16GB DDR4 · GTX 1060 6GB · Pop!_OS/Ubuntu
> **Target**: LangGraph + n8n Hybrid Architecture

---

## ✅ COMPLETED

### Phase 0 — Foundation (Day 1–2)

- [X] **Ollama Installation** — Installed successfully to /usr/local

  - Service enabled and running as systemd service
  - User permissions configured (render, video, ollama groups)
- [X] **Pull Models**

  - [X] `ollama pull qwen2.5:7b-instruct-q4_K_M` (~4.1GB VRAM)
  - [X] `ollama pull nomic-embed-text` (~270MB, embeddings for RAG)
  - [X] GPU offload verified with `--verbose` flag
- [X] **Project Directory & Git**

  - [X] Created ~/Projects/EVI/ (note: actual path, not ~/agent-server)
  - [X] Git repository initialized
  - [X] .env.example created with all required variables
- [X] **Docker Compose Setup (Configuration)**

  - [X] docker-compose.yml created with all 4 services:
    - [X] Qdrant (vector DB, 1GB mem limit)
    - [X] n8n (orchestration + integrations, 512MB mem limit)
    - [X] agent-api (FastAPI service, 2GB mem limit, built from ./agent)
    - [X] Postgres (metadata storage, 512MB mem limit)
  - [X] Environment variables configured
  - [X] Volume mappings set up for all services
- [X] **Project Structure**

  - [X] Created agent/ directory with Dockerfile and main.py stub
  - [X] Set up watched_folders/ with all subdirectories: inbox, university, code, pdfs, unsorted
  - [X] Created data/ volumes: n8n/, postgres/, qdrant/
- [X] **Agent Dockerfile & Dependencies**

  - [X] agent/Dockerfile created with Python 3.11
  - [X] Dependencies specified: FastAPI, uvicorn, LangChain, LangGraph, Ollama, Qdrant, httpx

### Next: Start Docker Compose & Wire LangGraph Core

---

## 🚧 IN PROGRESS / TODO

### Phase 0 — Foundation (Remaining)

- [X] **Docker Compose Execution**
  - [X] Copy .env.example to .env and fill in secrets
  - [X] Build and start containers: `docker compose up -d`
  - [X] Verify all 4 services running: `docker ps`
  - [X] Qdrant running at http://localhost:6333 (API docs at /redoc)
  - [X] n8n running at http://localhost:5678
  - [X] agent-api running at http://localhost:8000/
  - [X] Verify RAM usage < 5GB: `free -h && docker stats`

---

### Phase 1 — ReAct Agent Core (Day 3–5)

- [X] **LangGraph Implementation**

  - [X] Create `agent/graph.py` with StateGraph and ReAct loop
  - [X] Implement `agent_node()` for reasoning
  - [X] Implement `should_continue()` router (tool vs end)
  - [X] Add safety guards (max iterations = 10)
  - [X] Bind Qwen 7B model with tool-calling mode
  - [X] Test graph with simple query
- [X] **FastAPI Entrypoint** (Partial — Scaffolded)

  - [X] `agent/main.py` created with FastAPI app
  - [X] Wire LangGraph to `/chat` endpoint (currently stubbed)
  - [X] Implement `/run-task` endpoint for scheduled/triggered tasks
  - [X] Health check endpoint: `GET /` returns status
- [X] **Tool: File Organizer**

  - [X] Create `agent/tools/__init__.py`
  - [X] Create `agent/tools/file_organizer.py`
  - [X] Implement file classification logic (university, code, pdfs, unsorted)
  - [X] Add `organize_inbox()` tool with dry-run mode
  - [X] Add deduplication logic (MD5 hash for filename collisions)
- [ ] **Memory System**

  - [X] Create `agent/memory.py` with BoundedMemory class
  - [X] Keep message history ≤ 8 pairs to cap RAM usage
- [X] **Integration Test**

  - [X] Start docker compose with all services running
  - [X] Send simple chat query: `curl -X POST http://localhost:8000/chat -d '{"message": "Hello"}'`
  - [X] Verify LangGraph loop completes successfully

---

### Phase 2 — RAG System for University Notes (Day 6–10)

- [ ] **Vector Database Setup**

  - [ ] Confirm Qdrant running in docker compose
  - [ ] Create "university_notes" collection (768-dim, COSINE distance)
- [ ] **Tool: PDF Ingestion & RAG**

  - [ ] Create `agent/tools/rag_tool.py`
  - [ ] Implement `ingest_university_folder()` tool
  - [ ] Use PyPDFLoader with recursive chunking (512 chunk size, 64 overlap)
  - [ ] Batch ingest to Qdrant (50 docs per batch)
  - [ ] Implement `query_university_notes()` tool (similarity search + scoring)
- [ ] **Auto-Watch Script**

  - [ ] Create `scripts/watch_and_ingest.sh` using inotifywait
  - [ ] Auto-ingest new PDFs to Qdrant when dropped in watched_folders/university
  - [ ] Create systemd user service: agent-watcher
  - [ ] Install dependency: `sudo apt install inotify-tools`
- [ ] **Integration Test**

  - [ ] Drop sample lecture PDF into watched_folders/university/
  - [ ] Test query: "Summarize the key concepts from Operating Systems notes"
  - [ ] Verify retrieval accuracy and response quality

---

### Phase 3 — Google Calendar via n8n (Day 11–14)

- [ ] **n8n Configuration**

  - [ ] Access n8n UI at http://localhost:5678
  - [ ] Set up Google Calendar OAuth (requires service account or user OAuth)
  - [ ] Configure webhook: POST /webhook/calendar
- [ ] **n8n Workflow Nodes**

  - [ ] Create workflow with Switch node for action routing:
    - [ ] "schedule_event" → Google Calendar Create Event
    - [ ] "list_events" → Google Calendar Get Events
    - [ ] "agent_query" → HTTP call back to agent-api:8000
- [ ] **Tool: Calendar Integration**

  - [ ] Create `agent/tools/calendar_tool.py`
  - [ ] Implement `create_calendar_event()` tool (delegates to n8n)
  - [ ] Implement `list_upcoming_events()` tool
  - [ ] Test: Schedule a study session via agent chat

---

### Phase 4 — Performance & Polish (Day 15+)

- [ ] **Ollama VRAM Governor**

  - [ ] Create /etc/systemd/system/ollama.service.d/override.conf
  - [ ] Set environment variables: MAX_LOADED_MODELS=1, FLASH_ATTENTION=1
  - [ ] Restart ollama service and verify VRAM reduction
- [ ] **Swap Safety Net**

  - [ ] Create 8GB swap file at /swapfile
  - [ ] Set vm.swappiness=10 to avoid excessive swapping
  - [ ] Persist swap configuration in /etc/fstab
- [ ] **GitHub Copilot Integration**

  - [ ] Update VS Code settings for auto-completions
  - [ ] Use Copilot for boilerplate, tests, scaffolding
  - [ ] Reserve local LLM for runtime reasoning & private data
- [ ] **Monitoring & Logging**

  - [ ] Add request logging to FastAPI
  - [ ] Monitor docker stats regularly
  - [ ] Create simple dashboard view of agent uptime
- [ ] **Remote Access (Optional)**

  - [ ] Set up Tailscale for secure remote access
  - [ ] Configure n8n workflows for background jobs

---

## Timeline Summary

| Phase                | Days   | Status          | Priority |
| -------------------- | ------ | --------------- | -------- |
| Phase 0 (Foundation) | 1–2   | � 98% Complete | CRITICAL |
| Phase 1 (ReAct Core) | 3–5   | 🟡 In Progress  | HIGH     |
| Phase 2 (RAG System) | 6–10  | 🔵 Blocked      | HIGH     |
| Phase 3 (Calendar)   | 11–14 | 🔵 Blocked      | MEDIUM   |
| Phase 4 (Polish)     | 15+    | 🔵 Blocked      | LOW      |

---

## Notes

- **Current Status**: Project structure fully set up, docker-compose ready to deploy. Awaiting execution.
- **Docker Compose Location**: ~/Projects/EVI/ (using this instead of ~/agent-server as originally planned)
- **Environment Secrets**: .env.example exists; need to create .env with actual credentials:
  - N8N_AUTH_USER, N8N_AUTH_PASSWORD
  - POSTGRES_PASSWORD
- **RAM Budget**: Target <5.5GB used during docker compose execution

---

## Current Project Structure (As Built)

```
~/Projects/EVI/
├── .env.example                  ✅ Created with all required vars
├── .env                          ⏳ Awaiting secrets
├── .git/                         ✅ Git repo initialized
├── .gitignore                    ✅ Created
├── docker-compose.yml            ✅ All 4 services configured
├── personal-ai-agent-server.md   ✅ Implementation plan (reference)
├── Progress.md                   ✅ This file
│
├── agent/
│   ├── Dockerfile                ✅ Python 3.11 + dependencies
│   ├── main.py                   🟡 FastAPI app (stubs only)
│   └── tools/
│       └── [EMPTY]               ⏳ Awaiting implementation
│
├── scripts/
│   └── [EMPTY]                   ⏳ Awaiting watch_and_ingest.sh
│
├── watched_folders/
│   ├── code/                     ✅ Directory created
│   ├── inbox/                    ✅ Directory created
│   ├── pdfs/                     ✅ Directory created
│   ├── university/               ✅ Directory created
│   └── unsorted/                 ✅ Directory created
│
└── data/
    ├── n8n/                      ✅ Volume ready
    ├── postgres/                 ✅ Volume ready
    └── qdrant/                   ✅ Volume ready (with existing data)
```

### What's Built

- ✅ Infrastructure: Docker Compose with all 4 microservices
- ✅ Configuration: Environment variables ready
- ✅ Project Layout: All directories and volumes prepared
- ✅ FastAPI Server: Main app initialized
- ✅ Docker Image: Ready to build

### What's Pending

- ✅ Secrets: .env populated and services running
- ✅ Docker Startup: All 4 services running successfully
- ⏳ LangGraph Core: graph.py not implemented
- ⏳ Tools: file_organizer, rag_tool, calendar_tool not built
- ⏳ Memory: BoundedMemory class not implemented
- ⏳ Watchers: inotifywait script not created

---

## 🚀 Next Immediate Actions (Priority Order)

1. **[CRITICAL]** Verify RAM usage: `free -h && docker stats` (target <5.5GB)
2. **[CRITICAL]** Implement `agent/graph.py` — core ReAct loop with Qwen 7B
3. **[CRITICAL]** Create `agent/tools/__init__.py` and `agent/tools/file_organizer.py`
4. **[HIGH]** Wire `/chat` endpoint in main.py to use graph.py + tools
5. **[HIGH]** Rebuild agent-api: `docker compose up -d --build agent-api`
6. **[HIGH]** Test Phase 1: Send chat query via curl and verify LangGraph execution
7. **[MEDIUM]** Add `agent/memory.py` — BoundedMemory for context management
8. **[MEDIUM]** Create `agent/tools/rag_tool.py` — PDF ingestion for Phase 2
