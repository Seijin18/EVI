# Design: evi-agent-runtime-v3

## Context assembly (4 blocks)

1. Bootstrap — `EVI_WORKSPACE/{USER,AGENTS,TOOLS}.md`
2. Session — Postgres messages + `session_tool_snapshots` JSON
3. Memory — `MEMORY.md`, `memory/YYYY-MM-DD.md`, contact `profile.md` when JID known
4. Skills — selective `skills/*/SKILL.md` by intent keywords

## RAM / ports

No new containers. Workspace on disk under `EVI_WORKSPACE` (default `EVI_PROJECT_ROOT/EVI_WORKSPACE`).

## Compaction

When `BoundedMemory` exceeds max pairs, `memory_flush.py` appends turn summary to daily log before trim.
