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

**Deferred (roadmap):** Compose Ollama profile, adapter WhatsApp Meta/Twilio, pool de
conexões Postgres, gating de tools — ver [`specs/roadmap.md`](specs/roadmap.md).
Auth deixou de ser deferida: virou parte do #31 (Etapa 12).

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

## Etapa 12 — runtime hardening (12 Ago 2026)

Revisão geral do sistema em 2026-08-12 encontrou três itens marcados **Done** que
não funcionam como descrito (dev bridge no container, fuso na tabela de datas,
comparação do heartbeat) e a base sem isolamento de sessão nem auth efetiva.
Roadmap reordenado: [`specs/roadmap.md`](specs/roadmap.md). Nada de feature nova
antes do #31.

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 31 | `evi-runtime-hardening` | Done | Arquivado 2026-08-12. Isolamento de sessão (+ 3 vazamentos correlatos: `_on_trim` pegajoso, `_reset_session` ignorando o arg, `/insight` global), auth nos 4 endpoints sem `Depends` + `EVI_REQUIRE_API_KEY`, serviços de dados em `127.0.0.1` (PG→5433, Qdrant com API key), `now_local()` no `_calendar_block`, deps pinadas (LangChain 0.3→1.3.15 validada), `build_background_llm` sem mutar env, `soft_fail` em 35 sites. Também corrigiu `test_session_lane_serializes`, que passava por timeout de barrier |

## Fila de propostas (pós-#31)

Uma proposta por vez, na ordem — ver [`specs/roadmap.md`](specs/roadmap.md) para o porquê.

| # | Change sugerido | Etapa | Resumo |
|---|-----------------|-------|--------|
| 32 | `evi-container-smoke-ci` | 14.1 | **Done** — arquivado 2026-08-12. Job `container` no CI + `evi-test container`. Reproduz o bug do dev bridge (`[KNOWN]` #33), acha `testing.cli.REPO_ROOT` = `/` (corrigido) e assegura bind/porta. Durante a implementação, rodá-lo sem isolar volumes corrompeu o Postgres de dev — recuperado com `pg_resetwal`; o script agora **aborta** se detectar bind mount de `./data` em escrita. |
| 33 | `evi-dev-bridge-decision` | 13.1 | Consertar `_REPO_ROOT` (`EVI_REPO_ROOT` + montar repo + `git`/`claude` na imagem) **ou** remover código e spec `dev-bridge`. Decisão do usuário. |
| 34 | `evi-tool-result-contract` | 13.2 | Resultado tipado (`ok: bool`) no lugar de `if "failed" in result.lower()`. Toca 26 tools + scripts Windmill. |
| 35 | `evi-test-coverage-core` | 14.2–14.7 | `calendar_tool`, `auth`, `telegram_poller`, `evolution_client`, `session_lane`, `db` (PG efêmero no CI). |
| 36 | `evi-small-correctness` | 13.3–13.5 | **Done** — arquivado 2026-08-12. Retry + motivo visível nos envios Telegram/WhatsApp, heartbeat sempre-verdadeiro, eviction do `evolution_seen_ids.json`. Promovido à frente da fila: `evi-telegram-verify.sh` falhou em produção porque uma instabilidade de rede de ~2 min fez `send_telegram_message` descartar a resposta em silêncio |
| 37 | `evi-prompt-injection-model` | 15 | Threat model + spec para conteúdo de terceiros que chega ao grafo principal. |
| 38 | `evi-background-execution` | 16 | Tarefas longas desacopladas do turno de chat; ack imediato + resultado depois. |

**Cortado do roadmap** (motivos em [`specs/roadmap.md`](specs/roadmap.md)): MCP servers
isolados, multimodal Llava/Whisper, cache Redis de embeddings.
