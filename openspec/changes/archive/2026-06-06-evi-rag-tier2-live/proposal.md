## Why

RAG smoke skips when Qdrant is down; no Tier 2 live harness for ingest+query.

## What Changes

- `run_rag(live_qdrant)` + `--live-qdrant` flag
- SCN-RAG-04; evi-test routes live RAG to agent-api container

**Out of scope:** New Qdrant collections beyond `university_notes`.
