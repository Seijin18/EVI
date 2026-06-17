# EVI — Implementation status

> **Updated:** June 2026  
> **Hardware:** i5-7400 · 16 GB RAM · GTX 1060 3GB  
> **Source of truth:** [`openspec/specs/`](openspec/specs/) · **Backlog:** [`openspec/BACKLOG.md`](openspec/BACKLOG.md)  
> **Verify:** `./scripts/evi-test smoke` · `openspec validate --specs`

## Stack (as-built)

| Layer | Component |
|-------|-----------|
| Agent | FastAPI + LangGraph ReAct (`agent/`) |
| LLM | Gemini `gemini-2.5-flash` (`EVI_LLM_PROVIDER=gemini`); fallback Ollama `qwen2.5:3b-instruct-q4_K_M` |
| Embeddings | Google `models/gemini-embedding-001` 3072 dim (`EVI_EMBED_PROVIDER=google`); fallback Ollama `nomic-embed-text` 768 dim |
| Orchestration | Windmill (`windmill/f/integrations/`) |
| WhatsApp | Evolution API → commitment queue |
| Remote | Telegram webhook or polling |
| Data | Postgres sessions + `pending_commitments` |
| Vector | Qdrant `university_notes` (secondary) |
| Ops | `GET /health`, `GET /metrics`, CI smoke |

## Completed (P0–P3 + Jun 2026)

- OpenSpec 7 domain specs, `evi-test` harness, smoke 13/13 offline
- Windmill: Calendar, Tasks (`gtasks`), Gmail, `list_events`, Telegram bridge
- WhatsApp: Evolution webhook, group whitelist, heuristic extract, Postgres queue
- Commitment loop: list/confirm/dismiss tools, Telegram digest (SCN-WA-12)
- Telegram: E2E reply (SCN-TG-02), direct schedule/list bypass, polling (SCN-TG-04)
- Evolution logs: `filtered_out`, `message_ts` (SCN-WA-13..15)
- WhatsApp control chat (`EVI_WHATSAPP_CONTROL_JIDS`), multichannel review, LLM extract fallback (SCN-WA-16)
- n8n removed; compose healthchecks (SCN-OPS-01)

## Active series (architecture review)

Série jun/2026 + Etapa 4 ops **completas** — ver [`openspec/BACKLOG.md`](openspec/BACKLOG.md). Etapa 4: `/health`, `/metrics`, GitHub Actions CI, RAG live harness. Próximo: Etapa 5 memória longa (`data-long-memory`).

## Deferred memory (Etapa 5)

[`openspec/specs/data-long-memory/spec.md`](openspec/specs/data-long-memory/spec.md) — hot layer (Postgres) done; cold FS per contact + Neo4j graph planned. See [`openspec/BACKLOG.md`](openspec/BACKLOG.md) #15–17.

## Deferred ops / other

[`openspec/specs/roadmap.md`](openspec/specs/roadmap.md) — Etapa 4 ops, MCP isolado, multimodal.

## Historical detail

Long-form guide (legacy sections): [`personal-ai-agent-server.md`](personal-ai-agent-server.md) — prefer specs for current behavior.
