# Personal AI Agent Server — Implementation Progress (V2)

> **Start Date**: May 12, 2026  
> **Current Date**: June 5, 2026  
> **Hardware**: Intel i5-7400 · 16GB DDR4 · GTX 1060 3GB · Pop!_OS/Ubuntu  
> **Target Architecture**: LangGraph + Windmill + Evolution API + Ollama + Qdrant + Postgres (Neo4j/MCP deferred)  
> **Source of truth**: `openspec/specs/` · Verify: `pytest tests/unit -q && ./scripts/evi-test smoke`

---

## ✅ COMPLETED (Phases 0–1)

### Phase 0 — Foundation (Infrastructure Setup)

- [x] **Ollama Installation** ✅
  - Service running as systemd with GPU offload enabled
  - Models installed: qwen2.5:3b-instruct-q4_K_M (~2.2GB VRAM)
  - VRAM governor configured: `OLLAMA_MAX_LOADED_MODELS=1`

- [x] **Models Preparation** ✅
  - `ollama pull qwen2.5:3b-instruct-q4_K_M` (reasoning)
  - `ollama pull nomic-embed-text` (embeddings, CPU-based)
  - Pre-staged: `llava:7b-q4_K_M` (vision, on-demand)
  - Pre-staged: `whisper-small` (audio transcription, CPU-based)

- [x] **Docker Compose Stack** ✅
  - Qdrant (vector DB, 1GB limit)
  - n8n (orchestration, 512MB)
  - Postgres (sessions, 512MB)
  - agent-api (FastAPI + LangGraph tools, 2GB)
  - Neo4j: **not in compose** (planned — see `openspec/specs/roadmap.md`)

- [x] **Project Structure** ✅
  - ~/Projects/EVI/ directory initialized
  - Git repository with .gitignore
  - watched_folders/ structure: inbox, inbox_ia (NEW), university, code, pdfs, unsorted
  - data/ volumes: qdrant, postgres, n8n
  - scripts/: `evi-test`, `watch_and_ingest.sh`, `copilot-dev-runner.sh`

- [x] **Environment Configuration** ✅
  - .env.example created with all service variables
  - n8n webhooks, DATABASE_URL, EVI_API_KEY, notes dir

### Phase 1 — ReAct Agent Core (Scaffolding)

- [x] **LangGraph Framework** ✅
  - ReAct loop with native LangChain tools (MCP subprocess layer deferred)
  - Safety guard: max 10 iterations
  - Tool registry: `agent/tools/registry.py`

- [x] **File Organizer Tool** ✅
  - Classifies files by extension + keywords
  - Supports dry-run mode (no file moves)
  - Deduplication via MD5 hash on collisions

- [x] **Memory** ✅
  - BoundedMemory (max 8 pairs) + optional Postgres `messages` table

- [x] **FastAPI Entrypoint** ✅
  - `/`, `/tools`, `/chat`, `/reset`, `/run-task`, `/note`, `/insight`
  - `/webhooks/telegram` (with optional `EVI_API_KEY`)

- [x] **Dockerfile** ✅
  - Python 3.11 base
  - Dependencies: LangChain, LangGraph, Ollama, Qdrant, httpx, FastAPI
  - Audio & vision dependencies staged (faster-whisper, librosa, PIL)

---

## ✅ RECENT (June 2026 — OpenSpec + productivity)

- [x] **OpenSpec** — 7 domain specs; Cursor rules (`openspec-planning`, `openspec-changes`, `openspec-workflow`); archived P0–P3 changes
- [x] **Test harness** — `./scripts/evi-test`, `docs/testing.md`, smoke 13/13 offline
- [x] **Windmill Google Calendar** — `schedule_event` + `WINDMILL_GCAL_RESOURCE` + `WINDMILL_CALENDAR_ID` (calendário EVI)
- [x] **Windmill Google Tasks + Gmail** — `create_task.py`, `summarize_inbox.py`; OAuth via resource **gcloud** (Tasks) e **gmail**
- [x] **WhatsApp processor** — fixture + Evolution webhook + group whitelist (`EVI_WHATSAPP_GROUP_WHITELIST`)
- [x] **Commitment inbox** — Postgres `pending_commitments`, priority heuristics, Evolution INSERT + `queued` response
- [x] **Commitment review (chat)** — `list_pending_commitments`, `confirm_commitments`, `dismiss_commitments` in registry + graph hint
- [x] **Commitment notifications** — optional Telegram digest (`commitment_notify.py`) on threshold / high priority
- [x] **n8n removed** — `integrations-n8n` spec deleted; orchestration = Windmill only
- [x] **Evolution API** — compose + `/webhooks/evolution` + `evi-test evolution`
- [x] **Telegram bridge** — `POST /webhooks/telegram` + Windmill `telegram_to_evi`
- [x] **Batch ingest** — `ingest_university_folder` + parametrized watcher

- [x] **Commitment close-loop** — `confirm_commitments` → Calendar + Google Tasks; `evi-test commitments`; archived `2026-06-05-evi-commitment-close-loop`

**OpenSpec:** zero active changes · `openspec validate --specs` 7/7 · smoke 13/13

- [x] **Telegram E2E** — reply loop SCN-TG-02, digest SCN-WA-12, `scripts/evi-telegram-verify.sh`; archived `2026-06-05-evi-telegram-digest-e2e`

**Next planned changes:** `evi-windmill-live-verify` (Gmail/tasks live Tier 2) → `evi-compose-healthchecks`

---

## 🚧 IN PROGRESS / READY TO START

### Phase 2 — Hybrid Data Layer (partial)

**Status**: RAG tools implemented · Neo4j not started

#### Qdrant Vector Store
- [x] `university_notes` collection (768-dim, COSINE) — auto-created on startup
- [x] `ingest_university_pdf` + `query_university_notes` tools
- [ ] Batch `ingest_university_folder()` tool
- [ ] Auto-watcher production systemd service

#### Neo4j Knowledge Graph (NEW)
- [ ] Neo4j community container setup
  - APOC plugin enabled for graph algorithms
  - Memory limits: 1024m heap, 512m pagecache
- [ ] `graph_tool.py` implementation
  - Entity management (Algorithm, Theorem, Topic nodes)
  - Relationship creation (USES, DEPENDS_ON, EXPLAINS)
  - Path finding for reasoning (shortestPath queries)
- [ ] LLM-powered entity extraction from PDFs
  - Extract concepts + relationships during ingestion
  - Link documents → knowledge graph nodes

#### Auto-Ingest Watcher (Existing)
- [ ] scripts/watch_and_ingest.sh using inotifywait
- [ ] Auto-trigger `ingest_university_folder()` on new PDFs
- [ ] Systemd user service setup

---

### Phase 3 — MCP Orchestration Layer (READY — Week 3)

**Status**: Architecture Designed · Ready for Implementation

#### MCP Configuration
- [ ] Create `mcp-config.json` with three MCP servers:
  - **Filesystem Server**: organize_inbox, file operations
  - **Memory Router**: save_user_fact, recall_user_facts, link_concept_to_user
  - **RAG Server**: query_university_notes, query_knowledge_graph

#### MCP Servers Creation
- [ ] `mcp_servers/filesystem_server.py`
  - Subprocess running file operations in isolation
  - 300MB memory target
- [ ] `mcp_servers/memory_router_server.py`
  - PostgreSQL connection for short-term
  - Neo4j connection for mid-term facts
  - Tool dispatch via stdin/stdout
- [ ] `mcp_servers/rag_server.py`
  - Qdrant + Neo4j combined queries
  - Semantic search + graph path finding

#### MCP Client Integration
- [ ] `mcp_client.py` implementation
  - Start all MCP servers as subprocesses
  - Route tool calls by name
  - Handle stdin/stdout JSON communication
- [ ] Update `graph.py` to use MCP client
  - Load mcp-config.json
  - Bind MCP tools to LLM

#### Postgres Conversation History
- [ ] Schema for messages table:
  - timestamp, role (user/assistant), content, metadata
- [ ] Integration with TriLayerMemory
  - `add_message_short_term()` → Postgres insert
  - `get_context_window()` → last N pairs

#### Windmill integrations (replaces n8n)
- [x] Google Calendar OAuth + `schedule_event` live
- [x] Google Tasks OAuth (Windmill **gcloud** resource + Tasks API scope)
- [x] Gmail OAuth + `summarize_inbox` script
- [ ] Live Tier 2: `evi-test tasks --live-windmill`, `evi-test email --live-windmill` (next change)

---

### Phase 4 — Remote UI & Multimodality (READY — Week 4)

**Status**: Tools Designed · Ready for Implementation

#### Audio Processing (Faster-Whisper on CPU)
- [ ] Update agent/Dockerfile
  - `pip install faster-whisper librosa soundfile`
- [ ] `audio_tool.py` implementation
  - WhisperModel loaded with device="cpu", compute_type="int8"
  - Transcribe with timestamps
  - Audio feature extraction (tempo, energy, spectral)

#### Vision Processing (Llava On-Demand)
- [ ] `vision_tool.py` implementation
  - Llava 7B Q4 loaded on first request
  - Base64 image encoding
  - Response + auto-unload (KEEP_ALIVE=0)
  - Frees VRAM after use

#### Telegram Bot Integration
- [ ] Create bot via @BotFather
- [ ] Set TELEGRAM_BOT_TOKEN in .env
- [ ] n8n Telegram node configuration
- [ ] Webhook routing to agent-api

#### Auto-Notes System (NEW — Core Feature)
- [ ] `note_manager.py` implementation
  - YAML frontmatter generation
  - Auto-notes: called at conversation end
  - Manual notes: user command triggered

##### AUTO-NOTES Flow
- [ ] Analyze conversation history at session end
- [ ] LLM extracts:
  - Key learnings (2-3 bullets)
  - Emerging questions (2 items)
  - Action items
  - Related concepts (tags)
- [ ] Save to `/watched_folders/inbox_ia/{timestamp}_auto_insight.md`
- [ ] Include metadata: date, tags, category

##### MANUAL-NOTES Flow
- [ ] User command: "IA, save this as study notes"
- [ ] Agent calls `save_note_manual(title, content, tags, category)`
- [ ] Structured Markdown with frontmatter
- [ ] Save to `/watched_folders/inbox_ia/`

---

### Phase 5 — GitHub Copilot CLI Integration (READY — Week 5+)

**Status**: Integration Plan Ready · For Heavy Dev Tasks

#### Copilot CLI Installation
- [ ] `npm install -g @github/copilot-cli`
- [ ] `copilot auth` with GitHub account
- [ ] Verify: `copilot --version`

#### Usage Patterns
- [ ] **EXPLAIN**: Understand docker/Python errors
- [ ] **SCAFFOLD**: Generate pytest test suites
- [ ] **BUILD**: Create new MCP server templates
- [ ] **DEBUG**: Troubleshoot agent issues
- [ ] **OPTIMIZE**: Performance recommendations
- [ ] **REFACTOR**: Code structure improvements

#### Integration Script
- [ ] `scripts/copilot-dev-runner.sh`
  - Wrapper for common copilot tasks
  - Reserve LOCAL LLM for:
    - Runtime agent reasoning
    - RAG queries on private data
    - Real-time inference

#### Recommended Workflow
- Use Copilot CLI for:
  - Boilerplate generation (MCP servers, tests)
  - Debugging complex errors
  - Documentation generation
- Keep Ollama (local) for:
  - Agent core reasoning
  - Private data queries
  - Inference on watched folders

---

## 📊 RAM Usage Tracking

### Current Allocation (Phase 0 Complete)
```
System:      2.0 GB ✅
Ollama:      2.2 GB ✅ (Qwen 3B Q4 loaded)
Qdrant:      0.1 GB (empty, allocated 1GB)
Neo4j:       0.2 GB (allocated 1.5GB)
n8n:         0.1 GB (allocated 512MB)
Postgres:    0.1 GB (allocated 512MB)
agent-api:   0.3 GB (allocated 2GB)
─────────────────────
Total Used:  ~7.3 GB / 16GB
Target:      ~12.7 GB (Phase 4 complete)
Headroom:    ~3.3 GB ✅
```

### VRAM Usage (GPU)
```
Qwen 3B Q4:   ~2.2 GB (persistent, full GPU offload)
nomic-embed:  ~0.6 GB when loaded (unload before LLM if tight)
Llava 7B:     UNLOADED (3GB VRAM — CPU-only or skip on this GPU)
Whisper:      CPU-based (no GPU)
Total VRAM:   ~2.2 GB / 3GB GTX 1060 ✅
```

---

## 🔄 Timeline Summary (V2)

| Week | Phase | Status | Deliverable |
|------|-------|--------|-------------|
| 1 | 0 + 1 | ✅ Partial | ReAct loop + File organizer |
| 2 | 2 | 🟡 Ready | RAG + Knowledge graph |
| 3 | 3 | 🟡 Ready | MCP orchestration + Memory layers |
| 4 | 4 | 🟡 Ready | Telegram + Whisper + Llava |
| 5+ | 5 | 🔵 Planned | Polish + GitHub Copilot CLI |

---

## 📝 Key Improvements (V2 vs V1)

### Architecture Upgrades
1. **MCP Layer**: Tools now isolated → modular, restartable, type-safe
2. **3-Layer Memory**: Replaces monolithic conversation history → scalable
3. **Neo4j Addition**: Enables reasoning chains → cross-document linking
4. **Faster-Whisper**: CPU-only transcription → frees VRAM for LLM
5. **Auto-Notes System**: Automatic insight capture → journaling + learning

### RAM Optimization
- Llava loaded on-demand (not persistent in VRAM)
- Whisper runs CPU-based (device="cpu", compute_type="int8")
- Total target: 12.7GB (up from 11.6GB) with 3.3GB headroom

### New Features
- **mcp-config.json**: Dynamic tool configuration
- **inbox_ia/**: Auto-generated notes output directory
- **GitHub Copilot CLI integration**: For heavy dev tasks
- **Auto-notes trigger**: On conversation end
- **Manual notes command**: User-initiated saving

---

## Running the Stack (Current State)

### Start Services
```bash
cd ~/Projects/EVI
cp .env.example .env  # Edit secrets
docker compose up -d
```

### Check Health
```bash
docker ps  # All services running?
free -h    # < 12GB RAM?
docker logs evi-agent-api-1  # Agent startup OK?
```

### First Test (When Ready)
```bash
curl -X POST http://localhost:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, organize my inbox for me"}'
```

---

## Action Items (Next Cycle)

### Immediate (This Week)
- [ ] Finalize mcp-config.json schema
- [ ] Test Neo4j startup with docker-compose
- [ ] Verify Qdrant + Postgres connectivity

### Short-term (Week 2–3)
- [ ] Implement Phase 2 RAG pipeline
- [ ] Create MCP server skeletons
- [ ] Test 3-layer memory with real data

### Medium-term (Week 4–5)
- [ ] Complete Telegram bot integration
- [ ] Validate audio + vision tools
- [ ] Deploy GitHub Copilot CLI helpers

---

**EVI Status**: ✅ Phase 0–1 Complete · 🟡 Phase 2–4 Ready · 🚀 Full Rollout in 4 Weeks
