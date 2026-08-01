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

## Etapa 6 — arquitetura modular (completa)

Spec: [`openspec/specs/providers/spec.md`](specs/providers/spec.md)

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 18 | `evi-modular-architecture` | Done | `agent/llm.py`, `agent/integrations/`, `agent/messaging/`; commit `1edef57` |
| 18.1 | `evi-windmill-client-inversion` | Done | Lógica HTTP para `integrations/windmill.py`; `windmill_client.py` virou shim; commit `4097f86` |
| 18.2 | `evi-commitment-capture-notify` | Done | `commitment_capture_notify.py`; notify control JID ao capturar; commit `4097f86` |
| 18.3 | `evi-providers-spec-sync` | Done | `openspec/specs/providers/spec.md`; AGENTS.md + BACKLOG.md; commit `4097f86` |

## Etapa 7 — cobertura e DX

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 19 | `evi-test-coverage-gap` | Done | 25 new tests; `telegram_notify.py` re-exports from `digest.py`; commit `6635c94` |
| 20 | `evi-ci-extended` | Done | CI: ruff lint + Tier-2 offline features; 11 ruff violations fixed; commit `6635c94` |
| 21 | `evi-daily-summary-tz-fix` | Done | `_today_str()` usa `ZoneInfo(EVI_TIMEZONE)`; commit `6635c94` |

## Etapa 8 — WhatsApp productivity

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 22 | `evi-confirm-all` | Done | `_CONFIRM_ALL`/`_DISMISS_ALL` + `_get_all_pending_ids()`; commit `6635c94` |
| 23 | `evi-extraction-expand` | Done | `_resolve_date`/`_resolve_time` com hoje, semana, weekdays PT, meses, períodos; commit `6635c94` |

## Etapa 9 — memória inteligente

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 24 | `evi-daily-summary-llm` | Done | `_llm_summarize()` quando `EVI_DAILY_SUMMARY_LLM=true`; commit `6635c94` |
| 25 | `evi-profile-auto-update` | Done | `profile_updater.py`; integrado em `whatsapp_control` + `telegram_handler`; commit `6635c94` |

**Deferred (roadmap):** `/chat`+`/run-task` auth obrigatória, Compose Ollama profile, Redis cache, MCP isolation, WhatsApp Meta/Twilio adapter — ver [`openspec/specs/roadmap.md`](specs/roadmap.md)

## Etapa 10 — autonomia + memória de contatos (17 Jun 2026)

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 26 | `evi-contact-learning` | Done | Arquivado 2026-06-17; contact tools, backfill, discovery, registro Postgres, replay de commitments — spec `data-long-memory` SCN-MEM-06..10 |
| 27 | `list_calendars` LangGraph tool | Done | Registrado em `agent/tools/calendar_tool.py`/`registry.py` junto do commit `bd012bf` |
| 28 | Heartbeat + background LLM tiers | Done | `services/heartbeat.py`, `build_background_llm()`; commit `bd012bf` |
| 29 | Session lane queue + slash commands | Done | `services/session_lane.py`, `services/chat_commands.py`; commit `bd012bf` |

## Etapa 11 — dev bridge multi-CLI (1 Ago 2026)

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 30 | `evi-dev-bridge-multi-cli` | Done | Arquivado 2026-08-01; corrige bug approve=plan (nunca aplicava mudanças), generaliza para `agent/devcli/` (Claude Code CLI default), spec nova `dev-bridge` |

## Etapa 12 — gap analysis vs. proposta original (1 Ago 2026)

Nenhum item priorizado ainda — registrados em [`openspec/specs/roadmap.md`](specs/roadmap.md#etapa-12--gap-analysis-vs-proposta-original-1-ago-2026) após comparação com a proposta original do EVI e o anúncio do Gemini Spark (Google I/O 2026).

| # | Item | Status | Notas |
|---|------|--------|-------|
| 31 | Web search tool | Backlog | Backend plugável (Tavily/SerpAPI/Brave); gap apontado pelo usuário |
| 32 | Gmail proactive background triage | Backlog | Estende `heartbeat.py`/cron pra Gmail, hoje só cobre WhatsApp |
| 33 | Skill auto-generation from behavior | Backlog | Inspirado no Gemini Spark; depende dos itens 31/32 primeiro |
| 34 | Tool subsetting by channel/intent | Backlog | Corrige o maior desperdício de tokens hoje (`bind_tools` sempre com as ~25 tools); não é MCP — ver nota no roadmap |
