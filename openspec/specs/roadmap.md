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

## Other deferred

| Item | Type | Notes |
|------|------|-------|
| `list_calendars` LangGraph tool | Feature | Windmill script exists; precisa de registry entry |
| `/chat` + `/run-task` API key auth | Security | Backward-compat; noop se `EVI_API_KEY` não configurado |
| Compose Ollama profile | Infrastructure | Profile `ollama` para stack completamente self-contained |
| MCP isolated servers | Architecture | After 3+ stable tools need isolated restart |
| Llava + Whisper | Feature | Multimodal remote |
| Redis embedding cache | Performance | Optional |
| WhatsApp live adapter | Integration | Meta / Twilio — facilitado pelo `BaseMessagingClient` |
