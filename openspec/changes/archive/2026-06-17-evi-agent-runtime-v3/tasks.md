# Tasks: evi-agent-runtime-v3

- [x] **0.1 Workspace bootstrap**
  - **Files:** `EVI_WORKSPACE/`, `agent/services/context_assembly.py`, `agent/graph.py`
  - **Verify:** `pytest tests/unit/test_context_assembly.py`

- [x] **0.2 Tool snapshots + audit**
  - **Files:** `agent/db.py`, `agent/main.py`, `agent/services/telegram_audit.py`
  - **Verify:** `pytest tests/unit/test_session_snapshots.py`

- [x] **0.3 Memory flush + compaction**
  - **Files:** `agent/memory.py`, `agent/services/memory_flush.py`
  - **Verify:** `pytest tests/unit/test_memory_flush.py`

- [x] **0.4 Runtime skills loader**
  - **Files:** `agent/services/skill_loader.py`, `EVI_WORKSPACE/skills/`
  - **Verify:** `pytest tests/unit/test_skill_loader.py`

- [x] **0.5 Heartbeat stub**
  - **Files:** `EVI_WORKSPACE/HEARTBEAT.md`, `agent/services/daily_summary.py`
  - **Verify:** `./scripts/evi-test smoke`
