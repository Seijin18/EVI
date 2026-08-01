# EVI roadmap (not yet implemented)

| Item | Type | Notes |
|------|------|-------|
| Commitment close-loop | Done | SCN-CHAT-04 task confirm; `evi-test commitments` |
| n8n spec removed | Done | Use `integrations-windmill` only; SCN-DEP-02 |
| Windmill live verify (Gmail/tasks) | Done | SCN-EMAIL-05, SCN-TASK-05 live harness |
| Telegram digest E2E | Done | SCN-WA-12 + SCN-TG-02 reply loop |
| Commitment audit | Done | `source_chat`, `list_scheduled_today` — série jun/2026 |
| Multichannel review | Done | `services/commitment_review/` |
| WhatsApp control chat | Done | `EVI_WHATSAPP_CONTROL_JIDS`, `[EVI]` prefix |
| WhatsApp reply on confirm | Cancelled | Use control-chat + multichannel review |
| Compose healthchecks | Done | SCN-OPS-01 |
| Unify tool registry | Done | `tools/registry.py` |

## Etapa 4 — ops (see BACKLOG)

| Item | Change |
|------|--------|
| Deep health | `evi-agent-health-deep` |
| Prometheus metrics | `evi-prometheus-metrics` |
| GitHub Actions smoke | `evi-github-actions-smoke` |
| RAG live harness | `evi-rag-tier2-live` |

## Etapa 5 — long memory (Done — see `data-long-memory` spec)

| Phase | Item | Notes |
|-------|------|-------|
| 5a | Contact filesystem | Done — `EVI_CONTACT_MEMORY_DIR`, `evi-test contact-memory` |
| 5a | Daily summary cron | Done — `/jobs/daily-summary`, Windmill `daily_summary.py` |
| 5b | Knowledge graph | Done — compose profile `graph`, `query_conversation_graph` tool |

## Etapa 6 — arquitetura modular (Done — see `providers` spec)

| Item | Change |
|------|--------|
| LLM/embed factory | `evi-modular-architecture` |
| Windmill HTTP inversion | `evi-windmill-client-inversion` |
| Commitment capture notify | `evi-commitment-capture-notify` |

## Etapa 7 — cobertura e DX (see BACKLOG #19–21)

| Item | Change |
|------|--------|
| Unit tests: whatsapp_control, handler, digest, log_retention | `evi-test-coverage-gap` |
| CI tier-2 + ruff | `evi-ci-extended` |
| Daily summary timezone fix | `evi-daily-summary-tz-fix` |

## Etapa 8 — WhatsApp productivity (see BACKLOG #22–23)

| Item | Change |
|------|--------|
| "confirmar tudo" bulk command | `evi-confirm-all` |
| Expanded extraction patterns (hoje, terça, próxima semana) | `evi-extraction-expand` |

## Etapa 9 — memória inteligente (see BACKLOG #24–25)

| Item | Change |
|------|--------|
| Daily summary with LLM | `evi-daily-summary-llm` |
| Profile.md auto-update | `evi-profile-auto-update` |

## Etapa 10 — autonomy + contact memory (Done — 17 Jun 2026)

| Item | Change |
|------|--------|
| Contact learning by name + Evolution backfill/discovery/registry | `evi-contact-learning` (archived 2026-06-17) |
| `list_calendars` LangGraph tool | Shipped with commit `bd012bf` — no longer deferred |
| Heartbeat + background LLM tiers | `services/heartbeat.py`, `build_background_llm()` |
| Session lane queue + slash commands | `services/session_lane.py`, `services/chat_commands.py` |

## Etapa 11 — dev bridge multi-CLI (Done — 1 Ago 2026)

| Item | Change |
|------|--------|
| Generic pluggable CLI backend (Claude Code default) + approve/apply bug fix | `evi-dev-bridge-multi-cli` (archived 2026-08-01) — see `specs/dev-bridge/spec.md` |

## Etapa 12 — gap analysis vs. proposta original (1 Ago 2026)

Levantado ao comparar o EVI com a proposta original (background + ativo) e com o anúncio do Gemini Spark (Google I/O 2026). Nenhum item abaixo tem change aberta ainda — registrar aqui até ser priorizado.

| Item | Type | Notes |
|------|------|-------|
| Web search tool | Feature | Backend plugável (Tavily/SerpAPI/Brave), mesmo padrão de `agent/integrations/`; registrar em `tools/registry.py` só quando `EVI_WEB_SEARCH_ENABLED=true`. Gap identificado pelo usuário — hoje o EVI só sabe o que está em RAG ou no treino do LLM |
| Gmail proactive background triage | Feature | Estender `heartbeat.py`/cron Windmill pra rodar `summarize_inbox` periodicamente e notificar o control chat só quando houver algo importante — mesmo padrão já usado pra `pending_commitments`. Fecha o gap real: hoje `daily_summary.py`/`heartbeat.py` só olham WhatsApp, nunca Gmail, apesar da proposta original pedir "processar mensagens e emails em background" |
| Skill auto-generation from behavior | Feature | Inspirado no "ghostwriter skill" do Gemini Spark (gera skill reutilizável a partir dos últimos N emails/mensagens do usuário). Depende de `EVI_WORKSPACE/skills/` já existente como formato; maior risco/esforço dos três, fazer depois dos outros dois |
| Tool subsetting by channel/intent | Performance | **Proposta formal aberta**: `evi-tool-routing` (`openspec/changes/evi-tool-routing/`) — heurística regex primeiro (mesmo padrão de `match_skills`), fallback opcional para `build_background_llm()` (Ollama) quando a heurística não bate em nada além do grupo `core`, mesmo padrão de `extract_commitment_with_fallback`. Não usa MCP — MCP é protocolo de transporte/descoberta, não reduz tokens enviados ao LLM |

## Other deferred

| Item | Type | Notes |
|------|------|-------|
| `/chat` + `/run-task` API key auth | Security | Backward-compat; noop se `EVI_API_KEY` não configurado |
| Compose Ollama profile | Infrastructure | Profile `ollama` para stack completamente self-contained |
| MCP isolated servers | Architecture | After 3+ stable tools need isolated restart — isolamento de processo, não relacionado a custo de tokens (ver Etapa 12) |
| Llava + Whisper | Feature | Multimodal remote |
| Redis embedding cache | Performance | Optional |
| WhatsApp live adapter | Integration | Meta / Twilio — facilitado pelo `BaseMessagingClient` |
