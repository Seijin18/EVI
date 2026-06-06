# EVI — Implementation status

> **Updated:** June 2026  
> **Hardware:** i5-7400 · 16 GB RAM · GTX 1060 3GB  
> **Source of truth:** [`openspec/specs/`](openspec/specs/) · **Backlog:** [`openspec/BACKLOG.md`](openspec/BACKLOG.md)  
> **Verify:** `./scripts/evi-test smoke` · `openspec validate --specs`

## Stack (as-built)

| Layer | Component |
|-------|-----------|
| Agent | FastAPI + LangGraph ReAct (`agent/`) |
| LLM | Ollama `qwen2.5:3b-instruct-q4_K_M` |
| Orchestration | Windmill (`windmill/f/integrations/`) |
| WhatsApp | Evolution API → commitment queue |
| Remote | Telegram webhook or polling |
| Data | Postgres sessions + `pending_commitments` |
| Vector | Qdrant `university_notes` (secondary) |

## Completed (P0–P3 + Jun 2026)

- OpenSpec 7 domain specs, `evi-test` harness, smoke 13/13 offline
- Windmill: Calendar, Tasks (`gtasks`), Gmail, `list_events`, Telegram bridge
- WhatsApp: Evolution webhook, group whitelist, heuristic extract, Postgres queue
- Commitment loop: list/confirm/dismiss tools, Telegram digest (SCN-WA-12)
- Telegram: E2E reply (SCN-TG-02), direct schedule/list bypass, polling (SCN-TG-04)
- Evolution logs: `filtered_out`, `message_ts` (SCN-WA-13..15)
- n8n removed; compose healthchecks (SCN-OPS-01)

## Active series (architecture review)

See [`openspec/BACKLOG.md`](openspec/BACKLOG.md). Done: baseline-v2, multichannel review, audit, control chat. Next: `evi-whatsapp-llm-extract`.

## Deferred

[`openspec/specs/roadmap.md`](openspec/specs/roadmap.md) — Neo4j, MCP isolado, multimodal, Prometheus, CI.

## Historical detail

Long-form guide (legacy sections): [`personal-ai-agent-server.md`](personal-ai-agent-server.md) — prefer specs for current behavior.
