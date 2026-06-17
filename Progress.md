# EVI — Progresso de desenvolvimento

> **Atualizado:** 17 Jun 2026  
> **README / arquitetura:** [`README.md`](README.md)  
> **Requisitos:** [`openspec/specs/`](openspec/specs/) · **Backlog:** [`openspec/BACKLOG.md`](openspec/BACKLOG.md) · **Adiado:** [`openspec/specs/roadmap.md`](openspec/specs/roadmap.md)  
> **Verify:** `./scripts/evi-test smoke` (14/14) · `openspec validate --specs`

---

## Resumo executivo

| Área | Status |
|------|--------|
| Core agent + Windmill | **Done** |
| WhatsApp ingest + control | **Done** |
| Telegram + digest | **Done** |
| Runtime v3 (LLM-first inbox/calendar) | **Done** (Jun 2026) |
| Memória longa (FS + Neo4j) | **Done** |
| Ops (health, metrics, CI) | **Done** |
| Roadmap deferido | Ver tabela abaixo |

**Foco atual:** operação e polish (OAuth Windmill, E2E live); novos changes só via [`openspec/BACKLOG.md`](openspec/BACKLOG.md) quando priorizado.

---

## Stack (as-built)

| Camada | Componente |
|--------|------------|
| Agent | FastAPI + LangGraph ReAct (`agent/`) |
| LLM | Gemini `gemini-2.5-flash` (`EVI_LLM_PROVIDER=gemini`); fallback Ollama `qwen2.5:3b-instruct-q4_K_M` |
| Embeddings | Google `gemini-embedding-001` 3072d; fallback Ollama `nomic-embed-text` |
| Orquestração | Windmill (`windmill/f/integrations/`) |
| WhatsApp | Evolution API → fila + control chat |
| Remote | Telegram webhook ou polling |
| Dados | Postgres, Qdrant, contact FS, Neo4j (opcional) |
| Runtime v3 | `EVI_WORKSPACE/`, context assembly, tool snapshots |

---

## Matriz de features

### Implementado

| Feature | Verify / spec |
|---------|----------------|
| File organizer | `./scripts/evi-test file-organizer` · SCN-FO-01 |
| RAG universidade | `./scripts/evi-test rag` · `data-rag` |
| Calendar create/list | `./scripts/evi-test calendar-list` · `on_date` / dias calendário |
| Tasks create/list | `./scripts/evi-test tasks` · `list_tasks` tool |
| Gmail summarize/delete | `./scripts/evi-test email` · `inbox-ux` |
| Commitment queue + review | `./scripts/evi-test commitments` |
| WhatsApp Evolution pipeline | `./scripts/evi-test whatsapp` · `evolution` |
| WhatsApp control + LLM extract | `test_whatsapp_control.py`, `test_whatsapp_llm_extract.py` |
| Telegram E2E | `./scripts/evi-telegram-verify.sh` |
| Contact memory + daily summary | `./scripts/evi-test contact-memory` · `daily-summary` |
| Knowledge graph | `./scripts/evi-test graph` (Neo4j profile) |
| Health + metrics + CI | `./scripts/evi-test health` · `.github/workflows/ci.yml` |
| Runtime v3 + inbox UX | `./scripts/evi-test runtime-v3` · `inbox-ux` |
| Providers modulares | `test_llm_factory.py`, `test_integration_factory.py` |

### Planejado (roadmap)

| Feature | Prioridade | Referência |
|---------|------------|------------|
| `list_calendars` LangGraph tool | Média | `roadmap.md` |
| API key auth obrigatória em `/chat` | Baixa | `roadmap.md` |
| Compose profile Ollama | Baixa | Infra |
| MCP servers isolados | Baixa | Arquitetura |
| Multimodal (Llava, Whisper) | Baixa | `roadmap.md` |
| Redis cache embeddings | Baixa | Performance |
| WhatsApp Meta/Twilio adapter | Baixa | `providers` spec |
| Heartbeat cron em produção | Média | `EVI_HEARTBEAT_ENABLED` |

---

## Etapas de rollout

Legenda: **Done** · **—** (não iniciado / deferido)

| Etapa | Tema | Status | Entregas principais |
|-------|------|--------|---------------------|
| P0–P3 | Foundation | **Done** | Compose, LangGraph, file organizer, RAG base |
| 1–9 | Série WhatsApp jun/2026 | **Done** | Observability, multichannel review, control chat, list_events spec, DX OpenSpec |
| 4 | Ops | **Done** | `/health`, `/metrics`, CI, RAG live harness |
| 4.5 | Bugfix Telegram | **Done** | Audit/persist LLM, fixtures Windmill |
| 5 | Memória longa | **Done** | Contact FS, daily summary, Neo4j graph |
| 6 | Arquitetura modular | **Done** | `llm.py`, `integrations/`, `messaging/` |
| 7 | Cobertura + DX | **Done** | +25 tests, CI extended, TZ daily summary |
| 8 | WhatsApp productivity | **Done** | confirmar/dispensar tudo, extração expandida |
| 9 | Memória inteligente | **Done** | Daily summary LLM, profile auto-update |
| **10** | **Runtime v3 + inbox** | **Done** | Workspace, context assembly, delete_by_query, LLM-first control, E2E harness |
| 11+ | Roadmap deferido | **—** | Ver matriz “Planejado” |

### Série Runtime v3 (17 Jun 2026) — Done

| Change | Entrega |
|--------|---------|
| `evi-agent-runtime-v3` | `EVI_WORKSPACE`, context assembly, memory flush, skills |
| `evi-llm-orchestration-inbox` | `delete_emails_by_query`, session snapshots, direct handlers off |
| `evi-whatsapp-llm-control` | evolution_filter, ingest conservador, control → grafo |
| `evi-v3-e2e-verification` | `runtime-v3`, `inbox-ux`, CI, docs/testing |

Arquivos: `openspec/changes/archive/2026-06-17-*`

---

## Checklist de verificação (release)

```bash
# Tier 1
PYTHONPATH=agent python3 -m pytest tests/unit -q

# Tier 2 offline
./scripts/evi-test smoke

# Tier 2 runtime v3
./scripts/evi-test runtime-v3
./scripts/evi-test inbox-ux

# Specs
openspec validate --specs

# Live (opcional, stack + OAuth)
./scripts/evi-telegram-verify.sh
./scripts/evi-inbox-ux-verify.sh
./scripts/evi-test email --live-windmill
./scripts/evi-test calendar-list --live-windmill
```

---

## Histórico / documentação legada

O guia longo V2 (n8n, MCP, fases semanais) foi **substituído** por este fluxo:

- **Arquitetura e features:** [`README.md`](README.md)
- **Requisitos normativos:** [`openspec/specs/`](openspec/specs/)
- **Testes:** [`docs/testing.md`](docs/testing.md)

[`personal-ai-agent-server.md`](personal-ai-agent-server.md) permanece como stub de redirecionamento.

---

## Como propor próximo trabalho

1. `openspec list` — preferir zero changes ativos  
2. Ler [`openspec/BACKLOG.md`](openspec/BACKLOG.md) e [`openspec/specs/roadmap.md`](openspec/specs/roadmap.md)  
3. `openspec new change <nome-kebab>` → implementar → verify → archive  
4. Atualizar **esta página** (etapa + matriz) ao arquivar change
