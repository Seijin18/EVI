# EVI OpenSpec backlog

**Source of truth for requirements:** `openspec/specs/`  
**One active change at a time:** `openspec list` must be empty before `openspec new change`.  
**O porquê de cada item:** [`specs/roadmap.md`](specs/roadmap.md) · revisão de produto:
[`docs/ux-review-2026-10.md`](../docs/ux-review-2026-10.md)

## Fila atual (revisão de produto — 10 Out 2026)

A base está fechada (Etapas 12–14, 17). A fila agora prioriza o que o usuário
percebe: o EVI passar a chegar até a pessoa em vez de esperar ser perguntado.
Antes, dois changes de verificação (V1, V2) para que tudo o que vem depois seja
validado em simulação fiel e medido no uso real. Em ordem — um por vez.
Changes já propostos por completo aguardam em [`queued/`](queued/README.md).

| # | Change | Etapa | Status | Resumo |
|---|--------|-------|--------|--------|
| 45 | `evi-sim-harness` | V1 | **Done** (2026-10-10) | Simulação do sistema montado: imagem de produção, poller/webhook reais, LLM real, scripts Windmill reais; falsos só nas bordas e no relógio. Cenários de uso real, falha e injeção; record/replay na CI |
| 46 | `evi-usage-validation` | V2 | **Done** (2026-10-10) | Validação com base no uso real: `turn_log`, sinais de resultado, relatório semanal com linha de base, sonda somente-leitura, falha real → cenário de simulação |
| 40 | `evi-morning-briefing` | 18 | **Done** (2026-10-10) | Briefing matinal determinístico no Telegram; responder age sobre os itens; falha parcial visível. Inclui delimitação de conteúdo externo (parte mínima do #37) |
| 41 | `evi-reminders` | 19 | **Done** (2026-10-10) | Lembretes com horário e recorrência disparados pelo próprio EVI (loop in-process); adiar/feito por resposta |
| 42 | `evi-reply-debts` | 20 | **Done** (2026-10-10) | Troca "compromissos" (0/37 confirmados) por: esperando sua resposta (determinístico), promessas suas, combinados com data |
| 43 | `evi-voice-input` | 21 | **Done** (2026-10-10) | Áudio do usuário no Telegram/controle WhatsApp → transcrição via Gemini |
| 44 | `evi-perceived-reliability` | 22 | **Done** (2026-10-10) | Watchdog externo, `/ajuda`, ack imediato em tool lenta, aviso de OAuth expirado |
| 37 | `evi-prompt-injection-model` | 23 | **Done** (2026-10-11) | Confirmação de tool destrutiva, allowlist por origem do turno, corpus adversarial |
| 38 | `evi-background-execution` | 24 | Condicional (pulado em 2026-10-11) | Tarefas longas desacopladas; abrir só se o ack do #44 não bastar |
| 47 | `evi-promise-context` | 25 | **Ativo** | Promessas avaliadas com contexto e atraso (padrão = gatilho, LLM OpenRouter ZDR = juiz, 96% nos casos reais); `llm_structured`; avaliador de LLM; canais fora das dívidas; dedupe da Evolution |
| 49 | `evi-security-review` | 27 | Na fila ([`queued/`](queued/)) — **próximo** | Modelo de ameaças, checklist ASVS/LLM, registro de achados; F1 já achado: `agent-api` aberto na LAN/tailnet sem chave; guardas de regressão na CI |
| 48 | `evi-contact-knowledge` | 26 | Na fila ([`queued/`](queued/)) | Perfil de contato estruturado (Fatos/Em aberto/Notas) por incremento com evidência; timeline com os dois lados; identidade `@lid`↔telefone; LLM OpenRouter ZDR |
| 50 | `evi-contact-names` | 28 | Na fila ([`queued/`](queued/)) | Agenda Google (People API, só leitura) sincronizada diariamente; nome do usuário nunca sobrescrito; pergunta semanal das conversas ativas sem nome |

**Deferido / cortado:** ver [`specs/roadmap.md`](specs/roadmap.md).

---

# Histórico

## Série WhatsApp (arquitetura revisada — jun 2026)

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

## Etapa 17 — import de agenda (12 Ago 2026)

| # | Change | Status | Notas |
|---|--------|--------|-------|
| 39 | `evi-contact-vcard-import` | Done | Arquivado 2026-08-12. ~1000 dos 2553 contatos apareciam só como número: o WhatsApp nunca envia os nomes da sua agenda, só o `pushName` que a própria pessoa escolheu. Parser vCard + casamento por `DDD + últimos 8 dígitos` (valida o nono dígito brasileiro; 1192 contatos reais → 1191 chaves, zero colisões). Job local, dry-run por padrão, `pushName` vira alias. |

## Etapas 13–14 — correção e testes (12 Ago 2026)

Fila da revisão de 2026-08-12, concluída exceto #37/#38 (reescopados).

| # | Change sugerido | Etapa | Resumo |
|---|-----------------|-------|--------|
| 32b | `evi-smoke-isolation-fix` | 14.1 | **Done** — arquivado 2026-08-12. O job `container` do #32 falhava na CI (sem `.env`) e, localmente, herdava o `.env` real e subia um segundo poller no bot (25 × HTTP 409). Fecha os dois canais restantes (`env_file: !reset []` + `--env-file /dev/null`) e reescreve a guarda para checar a consequência: a versão anterior testava a chave `env_file`, que o `compose config` nunca emite, e dava `[PASS]` sobre um config vazando. |
| 32 | `evi-container-smoke-ci` | 14.1 | **Done** — arquivado 2026-08-12. Job `container` no CI + `evi-test container`. Reproduz o bug do dev bridge (`[KNOWN]` #33), acha `testing.cli.REPO_ROOT` = `/` (corrigido) e assegura bind/porta. Durante a implementação, rodá-lo sem isolar volumes corrompeu o Postgres de dev — recuperado com `pg_resetwal`; o script agora **aborta** se detectar bind mount de `./data` em escrita. |
| 33 | `evi-remove-dev-bridge` | 13.1 | **Done** — arquivado 2026-08-12. Decisão: **remover**. Nunca executou no container; consertar exigiria repo montado em escrita + CLI de edição, com a fronteira de confiança sendo um JID de WhatsApp. Specs 10→9, smoke 14/14→13/13, `[KNOWN]` do container smoke eliminado. Tabelas `dev_jobs`/`dev_bridge_state` ficam vazias (sem DROP automático). |
| 34 | `evi-tool-result-contract` | 13.2 | **Done** — arquivado 2026-08-12. `ToolResult` + `parse_windmill_result` tolerando os 4 envelopes do Windmill. **Corrigiu bug ativo**: `_tool_succeeded` casava a substring `"criad"` e marcava compromisso como `scheduled` com o agendamento falhando. Scripts Windmill não tocados (adaptador só no agente). |
| 34b | Snapshots estruturados de sessão | 13.2 | Descopado do #34: exige `response_format="content_and_artifact"` do LangChain (conteúdo para o modelo, artifact para o código) — muda assinatura de tool e o ToolNode. Hoje `persist_tool_snapshots` grava `{"raw": prosa}` e o bloco SESSION TOOL SNAPSHOTS não tem ids. |
| 35 | `evi-test-coverage-core` | 14.2–14.7 | **Done** — arquivado 2026-08-12. +62 testes: `telegram_poller` (invariantes do loop), `evolution_client` (envio, echo guard, limite de contatos), `db` contra Postgres real (migrações, dedupe `ON CONFLICT`, transições de status), `main.py` (webhook Evolution). Postgres efêmero como service na CI. `calendar_tool`/`auth`/`session_lane` já cobertos em #31/#34. |
| 36 | `evi-small-correctness` | 13.3–13.5 | **Done** — arquivado 2026-08-12. Retry + motivo visível nos envios Telegram/WhatsApp, heartbeat sempre-verdadeiro, eviction do `evolution_seen_ids.json`. Promovido à frente da fila: `evi-telegram-verify.sh` falhou em produção porque uma instabilidade de rede de ~2 min fez `send_telegram_message` descartar a resposta em silêncio |
| 37 | `evi-prompt-injection-model` | 15 | **Reescopado em 2026-10-10** — delimitação de conteúdo externo foi para o #40; o restante (confirmação de tool destrutiva, allowlist por origem, corpus adversarial) está na fila atual. |
| 38 | `evi-background-execution` | 16 | **Reescopado em 2026-10-10** — ack imediato foi para o #44; o restante está na fila atual. |

**Cortado do roadmap** (motivos em [`specs/roadmap.md`](specs/roadmap.md)): MCP servers
isolados, multimodal Llava/Whisper, cache Redis de embeddings.
