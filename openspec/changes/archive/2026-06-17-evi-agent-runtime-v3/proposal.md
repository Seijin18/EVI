## Why

EVI direct handlers bypass LangGraph, blocking multi-tool orchestration and session memory. OpenClaw-style context assembly (workspace bootstrap, tool snapshots, memory flush) enables LLM-first UX for Gmail and WhatsApp control.

## What Changes

- `context_assembly.py` + `EVI_WORKSPACE/` bootstrap files
- Postgres `session_tool_snapshots` + audit tool arrays
- Memory flush before bounded-memory compaction
- Runtime skill loader (selective injection)
- Heartbeat stub + `HEARTBEAT.md`

**Out of scope:** Neo4j required; browser automation; Node gateway rewrite.

## Impact

`agent/graph.py`, `agent/main.py`, `agent/db.py`, `openspec/specs/agent-api`, `data-long-memory`.
