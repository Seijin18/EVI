## Why

EVI stores commitments and short chat turns but lacks a formal spec for long-term conversation memory (per-contact filesystem + future knowledge graph). Architecture review agreed on phased design without implementing Neo4j in this cycle.

## What Changes

- New domain spec `data-long-memory` with SCN-MEM-* scenarios
- BACKLOG Etapa 5 queue; roadmap cleanup
- AGENTS.md domain map + Progress.md deferred section

**Out of scope:** Neo4j container, Graphiti, FS implementation, daily summary cron.

## Impact

Docs/specs only.
