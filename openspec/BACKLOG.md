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
| 7 | `evi-whatsapp-llm-extract` | Pending | Fallback LLM quando heurística falha |
| 8 | `evi-windmill-list-events-spec` | Partial | SCN-CAL-06 em baseline-v2; live harness pendente |
| 9 | `evi-dx-openspec-refresh` | Partial | BACKLOG.md + planning.mdc atualizados |

### Cancelado

| Change | Motivo |
|--------|--------|
| `evi-whatsapp-reply` | Ack automático no chat de origem não desejado; substituído por canal de controle + audit |

## Etapa 4 — sob demanda

| Change | Notas |
|--------|-------|
| `evi-agent-health-deep` | GET /health com deps |
| `evi-prometheus-metrics` | Métricas compose |
| `evi-github-actions-smoke` | CI |
| `evi-rag-tier2-live` | Qdrant live harness |
| Neo4j / MCP / multimodal | `openspec/specs/roadmap.md` |
