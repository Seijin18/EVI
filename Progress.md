# EVI — Progresso de desenvolvimento

> **Atualizado:** 10 Out 2026  
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
| Contrato de tools + cobertura do caminho crítico + import vCard | **Done** (12 Ago 2026) |
| Verificação realista (simulação + validação em uso real) | **Done** (10 Out 2026) — V1 + V2 |
| Assistente proativo (briefing, lembretes, voz) | **Done** — Etapas 18–23 (10–11 Out 2026) |

**Foco atual:** fila de 10 Out 2026 concluída; ativação em produção pendente (ver `openspec/queue-run.md`). Arquivados em 2026-10-10: #45
`evi-sim-harness` (V1), #46 `evi-usage-validation` (V2), #40 `evi-morning-briefing` (18),
#41 `evi-reminders` (19), #42 `evi-reply-debts` (20), #43 `evi-voice-input` (21), #44 `evi-perceived-reliability` (22), #37 `evi-prompt-injection-model` (23, em 11 Out), #47 `evi-promise-context` (25), #49 `evi-security-review` (27), #48 `evi-contact-knowledge` (26), #50 `evi-contact-names` (28), #51 `evi-ux-review` (29) — todos em 13 Out. Fila completa em [`openspec/BACKLOG.md`](openspec/BACKLOG.md);
porquês em [`openspec/specs/roadmap.md`](openspec/specs/roadmap.md).

> **Revisão de produto de 2026-10-10** ([`docs/ux-review-2026-10.md`](docs/ux-review-2026-10.md)).
> Avaliou o EVI pelo dia a dia do usuário. Achados: uso do `/chat` caiu de 520
> mensagens (jun) para 0 (set/out); 0 de 37 compromissos extraídos do WhatsApp foram
> confirmados; a stack ficou ~6 semanas parada sem ninguém notar. O EVI só age
> quando chamado. A fila foi reordenada para proatividade: briefing (18), lembretes
> (19), pendências de resposta (20), voz (21), confiabilidade percebida (22) — precedidos
> por simulação fiel (V1) e validação em uso real (V2).

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
| Tasks create/list/complete | `./scripts/evi-test tasks` · `list_tasks` / `complete_tasks` · `SIM-TASK-01` |
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

| Simulação do sistema montado (L2 `evi-sim`) | `./scripts/evi-sim run --tag critical --llm replay` · `testing` SCN-SIM-01..09 |
| Validação em uso real (L4): `turn_log`, `/bom` `/ruim`, relatório semanal, sonda | `test_turn_log.py`, `test_usage_report.py`, `test_probe.py` · SIM-USE-01/02 · `testing` SCN-USE-01..08 |
| Briefing matinal no Telegram + guarda `wrap_external` | `./scripts/evi-test briefing` · SIM-BRIEF-01..04 · `proactive` |
| Lembretes que disparam (loop in-process) | `test_reminders.py`, `test_reminder_loop.py` · SIM-REM-01..05 · `proactive` |
| Pendências de resposta, promessas e combinados com data | `test_reply_debts.py`, `test_promises.py`, `test_promise_context.py`, `test_llm_structured.py` · SIM-DEBT-01..09 · `messaging-whatsapp` |
| Mensagens de voz (Telegram + controle WhatsApp) | `test_transcribe.py` · SIM-VOICE-01..05 · `agent-api` |
| Confiabilidade percebida (watchdog, `/ajuda`, ack, OAuth no turno) | `test_watchdog.py`, `test_slow_ack.py` · SIM-REL-02..04 · `agent-api` |
| Defesa contra injeção (Telegram restrito, exclusão em 2 passos, guarda de escrita) | `./scripts/evi-test injection` · SIM-ADV-01..05 · `agent-api` |
| Contrato estruturado de tools (`ToolResult`) | `test_tool_result.py` · SCN-TOOL-01/02 |
| Import de agenda vCard | `test_vcard_import.py` · `data-long-memory` |

### Planejado (roadmap reordenado em 10 Out 2026)

| Feature | Etapa | Referência |
|---------|-------|------------|
| Watchdog externo, `/ajuda`, ack imediato, aviso de OAuth | 22 | BACKLOG #44 |
| Injeção de prompt — restante | 23 | BACKLOG #37 |
| Execução em background — restante | 24 | BACKLOG #38 |

**Cortados:** MCP servers isolados, Llava/Whisper **locais** (áudio reaberto via
Gemini na Etapa 21), cache Redis de embeddings, adapter WhatsApp Meta/Twilio
(Business API proíbe chatbot de uso geral desde 15/01/2026). Motivos em
`openspec/specs/roadmap.md`.

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
| **14.2** | **Cobertura do caminho crítico** | **Done** | poller, evolution_client, db (PG real), webhook Evolution — +62 testes |
| **17** | **Import de agenda (vCard)** | **Done** | Nomes da agenda por `.vcf`; casamento tolerante ao nono dígito |
| **V1** | **Simulação do sistema montado** | **Done** | `evi-sim-harness` — fakes nas bordas, código real no meio, LLM real, record/replay na CI |
| **V2** | **Validação em uso real** | **Done** | `evi-usage-validation` — `turn_log`, `/bom` `/ruim`, relatório semanal, sonda, `promote` |
| **18** | **Briefing matinal** | **Done** | `evi-morning-briefing` — determinístico, claim diário, `wrap_external` |
| **19** | **Lembretes** | **Done** | `evi-reminders` — loop in-process, recorrência, adiar/feito |
| **20** | **Pendências de resposta** | **Done** | `evi-reply-debts` — esperando resposta, promessas, combinados com data |
| **21** | **Voz** | **Done** | `evi-voice-input` — Telegram + controle WhatsApp via Gemini |
| **22** | **Confiabilidade percebida** | **Done** | `evi-perceived-reliability` — watchdog, `/ajuda`, ack, OAuth no turno |
| **23** | **Injeção (restante)** | **Done** | `evi-prompt-injection-model` — confirmação de exclusão, allowlist por origem, chat do Telegram restrito |
| **37** | **Concluir tarefas** | **Done** | `evi-task-complete` — `complete_tasks` (lote com exceções), IDs curtos em `list_tasks` |
| **35** | **Tarefas agendadas** | **Done** | `evi-scheduled-tasks` — pergunta agendada em linguagem natural, só leitura |
| **36** | **Precisão da extração** | **Done** | `evi-extraction-precision` — juiz LLM só no ambíguo para dívidas, juiz de tarefa sem data, reações do Telegram como feedback |
| **34** | **Esperando resposta deles** | **Done** | `evi-awaiting-their-reply` — follow-up semanal de quem não respondeu você, sem envio a terceiros |
| **33** | **Descoberta e prévia da noite** | **Done** | `evi-discovery-tips` — dica rotativa, prévia às 21h, 🔔 lembrar amanhã |
| **32** | **Resumo de WhatsApp rápido** | **Done** | `evi-whatsapp-summary-cache` — timeline local primeiro, Evolution em paralelo com orçamento, cache do resumo |
| **31** | **Briefing com um toque** | **Done** | `evi-briefing-buttons` — botões inline (✅/✖) e 👍/👎 no briefing, toque determinístico e com falha fechada |
| **30** | **Alertas de fonte fora** | **Done** | `evi-source-health-alerts` — WhatsApp no watchdog/sonda/`/health`, selo no topo do briefing, OAuth com ciclo de 7 dias explicado |
| **29** | **Revisão de usabilidade** | **Done** | `evi-ux-review` — briefing em HTML sem marcadores (duas renderizações), teto de 25 linhas, listas e acks limpos, fechamentos v2 |
| **28** | **Nomes de contato** | **Done** | `evi-contact-names` — agenda Google (People API, só leitura) → nomes, `name_source` (nome do usuário nunca sobrescrito), `@lid` herda o nome do telefone, pergunta semanal "nomeia N"/"ignora N" |
| **26** | **Conhecimento de contato** | **Done** | `evi-contact-knowledge` — perfil estruturado (Fatos/Em aberto/Notas) por atualização incremental com evidência, timeline com os dois lados, identidade `@lid`↔telefone, lote diário 03:30 |
| **25** | **Promessas com contexto** | **Done** | `evi-promise-context` — gatilho por padrão + juiz LLM com contexto (ZDR), fila `needs_eval`, varredura de cumprimento, `llm_structured`, avaliador |
| **27** | **Revisão de segurança** | **Done** | `evi-security-review` — modelo de ameaças, 28 achados, Windmill/agent-api em loopback, segredos rotacionados, auth por padrão, gates de CI |
| 24 | Background (restante) | **—** | Condicional: só se o ack do #44 não bastar |

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
