# EVI — Progresso de desenvolvimento

> **Atualizado:** 1 Ago 2026  
> **README / arquitetura:** [`README.md`](README.md)  
> **Requisitos:** [`openspec/specs/`](openspec/specs/) · **Backlog:** [`openspec/BACKLOG.md`](openspec/BACKLOG.md) · **Adiado:** [`openspec/specs/roadmap.md`](openspec/specs/roadmap.md)  
> **Verify:** `./scripts/evi-test smoke` (13/13) · `openspec validate --specs`

---

## Resumo executivo

| Área | Status |
|------|--------|
| Core agent + Windmill | **Done** |
| WhatsApp ingest + control | **Done** |
| Telegram + digest | **Done** |
| Runtime v3 (LLM-first inbox/calendar) | **Done** (Jun 2026) |
| Memória longa (FS + Neo4j + registro Postgres de contatos) | **Done** |
| Ops (health, metrics, CI) | **Done** |
| Autonomia (heartbeat, background LLM, session lane) | **Done** (17 Jun 2026) |
| Dev bridge multi-CLI | **Removido** (12 Ago 2026) — nunca rodou no container |
| Runtime hardening (isolamento de sessão, auth, fuso, deps) | **Done** (12 Ago 2026) |
| Roadmap deferido | Ver tabela abaixo |

**Foco atual:** #34 (contrato de tools) e #35 (cobertura). Fora da fila numerada,
o import de agenda por vCard resolve os contatos que aparecem só como número. Ver [`openspec/specs/roadmap.md`](openspec/specs/roadmap.md).

> **Revisão de 2026-08-12.** Uma revisão geral do sistema encontrou três itens antes
> marcados Done que não funcionavam como descrito. Dois foram corrigidos na Etapa 12:
> - ~~**Fuso horário**~~ — corrigido: `now_local()` com `ZoneInfo(EVI_TIMEZONE)` em
>   `_calendar_block()` e `iso_event_range()`.
> - ~~**Memória global entre sessões** e `EVI_API_KEY` vazio com quatro endpoints sem
>   `Depends`~~ — corrigidos.
> - ~~**Dev bridge**~~ — **removido** em `evi-remove-dev-bridge` (#33). `_REPO_ROOT`
>   resolvia para `/` no container e `scripts/` não estava na imagem, então
>   `dev approve` nunca funcionou. Consertar exigiria montar o repo em escrita e
>   instalar um CLI de edição de código, com a fronteira de confiança sendo um JID
>   de WhatsApp. Use `ssh`.
> - ~~**Heartbeat**~~ — corrigido em `evi-small-correctness` (#36), junto do retry nos
>   envios e da eviction do `seen_ids`.

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
| Contact learning + registro Postgres + discovery | `test_contact_registry.py`, `test_evolution_discovery.py` · `data-long-memory` |
| Commitment replay do ingest log | `test_commitment_replay.py` |
| Heartbeat + background LLM tiers | `services/heartbeat.py`, `build_background_llm()` |
| `list_calendars` LangGraph tool | `agent/tools/calendar_tool.py` |

### Planejado (roadmap reordenado em 12 Ago 2026)

| Feature | Prioridade | Referência |
|---------|------------|------------|
| Contrato estruturado de tools | Média | roadmap 13.2 · BACKLOG #34 |
| Cobertura: calendar_tool, auth, poller, db | Média | roadmap 14.2–14.7 · BACKLOG #35 |
| Threat model de prompt injection | Média | roadmap 15 · BACKLOG #37 |
| Execução em background | Média | roadmap 16 · BACKLOG #38 |
| Compose profile Ollama | Baixa | Infra |
| WhatsApp Meta/Twilio adapter | Baixa | `providers` spec |

**Cortados:** MCP servers isolados, multimodal (Llava/Whisper — incompatível com
GTX 1060 3 GB), cache Redis de embeddings. Motivos em `openspec/specs/roadmap.md`.

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
| **10.5** | **Autonomia + memória de contatos** | **Done** | Contact learning, registro Postgres, Evolution discovery, commitment replay, heartbeat, background LLM tiers |
| **11** | **Dev bridge multi-CLI** | **Revertida** | Removida em 12 Ago 2026 (`evi-remove-dev-bridge`): nunca executou no container (`_REPO_ROOT` = `/`) e o custo de segurança de consertar não se justificava |
| **12** | **Runtime hardening** | **Done** | Isolamento de sessão, auth nos 4 endpoints abertos, portas em `127.0.0.1` (PG→5433), fuso via `now_local()`, deps pinadas (LangChain 1.3.15), `soft_fail` em 35 sites |
| **13** | **Correções pequenas** | **Done** | Retry + motivo nos envios, heartbeat sempre-verdadeiro, eviction do `seen_ids` |
| **14.1** | **Container smoke no CI** | **Done** | Job `container`, `evi-test container`, guarda de isolamento de volumes |
| 14.2–16 | Cobertura, injeção, background | **—** | Ver `openspec/specs/roadmap.md` |

### Série Runtime v3 (17 Jun 2026) — Done

| Change | Entrega |
|--------|---------|
| `evi-agent-runtime-v3` | `EVI_WORKSPACE`, context assembly, memory flush, skills |
| `evi-llm-orchestration-inbox` | `delete_emails_by_query`, session snapshots, direct handlers off |
| `evi-whatsapp-llm-control` | evolution_filter, ingest conservador, control → grafo |
| `evi-v3-e2e-verification` | `runtime-v3`, `inbox-ux`, CI, docs/testing |
| `evi-contact-learning` | Contact tools, backfill, Evolution discovery, registro Postgres, commitment replay |

Arquivos: `openspec/changes/archive/2026-06-17-*`

### Série dev bridge (1 Ago 2026) — Done

| Change | Entrega |
|--------|---------|
| `evi-dev-bridge-multi-cli` | `agent/devcli/` (Protocol + factory), backend Claude Code CLI, fix bug approve sempre rodava `plan`, `dev mode plan\|default` |

Arquivos: `openspec/changes/archive/2026-08-01-evi-dev-bridge-multi-cli`

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
