# EVI OpenSpec backlog

**Source of truth for requirements:** `openspec/specs/`  
**One active change at a time:** `openspec list` must be empty before `openspec new change`.

## Série ativa (arquitetura revisada — jun 2026)

Substitui `evi-whatsapp-reply` (cancelado) por review multicanal + canal de controle WhatsApp.

| # | Change | Tipo | Resumo |
|---|--------|------|--------|
| 1 | `evi-as-built-baseline-v2` | Done | Arquivado 2026-06-06 |
| 2 | `evi-whatsapp-observability` | Done | SCN-WA-13..15 em spec + `evi-test evolution` |
| 3 | `evi-whatsapp-group-ops` | Done | `docs/evolution.md` seções whitelist + control |
| 4 | `evi-commitment-review-multichannel` | Done | `services/commitment_review/` |
| 5 | `evi-commitment-audit` | Done | `source_chat`, `list_scheduled_today` |
| 6 | `evi-whatsapp-control-chat` | Done | `EVI_WHATSAPP_CONTROL_JIDS`, prefixo `[EVI]` |
| 7 | `evi-whatsapp-llm-extract` | Done | Arquivado 2026-06-06; SCN-WA-16 |
| 8 | `evi-windmill-list-events-spec` | Done | Arquivado 2026-06-06; `evi-test calendar-list` |
| 9 | `evi-dx-openspec-refresh` | Done | Arquivado 2026-06-06; rules + cleanup |

**Nota:** Itens #2–6 foram implementados no commit `547667e` sem archives OpenSpec separados (código + specs em `openspec/specs/`).

### Cancelado

| Change | Motivo |
|--------|--------|
| `evi-whatsapp-reply` | Ack automático no chat de origem não desejado; substituído por canal de controle + audit |

## Etapa 4 — ops (completa)

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 10 | `evi-long-memory-architecture` | Done | Arquivado 2026-06-06; spec `data-long-memory` |
| 11 | `evi-agent-health-deep` | Done | Arquivado 2026-06-06; GET /health SCN-API-02 |
| 12 | `evi-prometheus-metrics` | Done | Arquivado 2026-06-06; `/metrics` SCN-OPS-03 |
| 13 | `evi-github-actions-smoke` | Done | Arquivado 2026-06-06; `.github/workflows/ci.yml` |
| 14 | `evi-rag-tier2-live` | Done | Arquivado 2026-06-06; `evi-test rag --live-qdrant` |

## Etapa 4.5 — bugfix + DX (completa)

| # | Change | Status | Notas |
|---|--------|--------|-------|
| — | `evi-telegram-audit-fix` | Done | LLM persist/audit; fixtures `windmill/`; `docs/testing.md` |

## Etapa 5 — memória longa (completa)

Spec: [`openspec/specs/data-long-memory/spec.md`](specs/data-long-memory/spec.md)

| # | Change | Fase | Status | Notas |
|---|--------|------|--------|-------|
| 15 | `evi-contact-filesystem-memory` | 5a | Done | `contact_filesystem.py`, ingest no webhook |
| 16 | `evi-daily-summary-windmill` | 5a | Done | `daily_summary.py`, `/jobs/daily-summary`, Windmill cron |
| 17 | `evi-conversation-graph-neo4j` | 5b | Done | Neo4j profile `graph`, `graph_tool.py`, `graph_sync.py` |

**Fora do repo:** Graphiti MCP. **Outros deferidos:** MCP isolado, multimodal — `openspec/specs/roadmap.md`
