# EVI testing guide

## Níveis de verificação

| Nível | O que roda de verdade | O que é falso | Comando | Quando |
|---|---|---|---|---|
| L0 unit | funções | tudo em volta | `pytest tests/unit -q` | sempre (CI) |
| L1 `evi-test <feature>` | módulos + fixtures | LLM, Windmill, rede | `./scripts/evi-test <feature>` | sempre (CI) |
| L1c container smoke | imagem montada, /health, /tools | dados | `./scripts/evi-test container` | CI |
| **L2 `evi-sim`** | imagem, poller Telegram, webhook Evolution, LangGraph, LLM real, scripts Windmill, Postgres | Google, Telegram API, Evolution API, relógio | `./scripts/evi-sim run` | antes de cada change ser arquivado (`--tag critical --repeat 3 --llm live`); CI em modo replay |
| L3 staging (futuro) | + Windmill server e schedules | Google | — | release maior |
| **L4 uso real** | tudo | nada | relatório semanal, sonda diária, `/bom` `/ruim` | contínuo — `evi-usage-validation` (`openspec/queued/`) |

Ciclo: L2 aprova antes de integrar → L4 mede depois → falha real vira cenário L2.

> **Atenção:** `scripts/evi-telegram-verify.sh`, `scripts/evi-inbox-ux-verify.sh` e
> as flags `--live-*` rodam contra as contas reais (Telegram, Gmail, Calendar) e
> gravam no Postgres de produção. Prefira o L2 `./scripts/evi-sim`; use esses só
> para diagnóstico pontual, não para validar change.

## evi-sim (L2)

Sobe a imagem de produção num projeto compose isolado (`evi-sim`) com fakes de
Google, Telegram API e Evolution API, e conduz cenários YAML contra ela.

```bash
./scripts/evi-sim guard                       # checa isolamento (não toca produção)
./scripts/evi-sim up [--llm live|record|replay]
./scripts/evi-sim run [--tag T] [--id SIM-RU-01] [--repeat N] \
    [--llm live|record|replay] [--max-llm-calls N]
./scripts/evi-sim report                      # último relatório
./scripts/evi-sim down                        # derruba e apaga volumes
```

`run` já faz `guard` + `up`. Gate de change:
`./scripts/evi-sim run --tag critical --repeat 3 --llm live`. Offline (igual ao CI):
`./scripts/evi-sim run --tag critical --llm replay`.

### Formato do cenário

Em `tests/sim/scenarios/<source>/*.yaml` (`real-usage`, `failure`, `adversarial`,
`smoke`, `whatsapp`). Validado por `agent/testing/sim/schema.py`; chave
desconhecida é erro. Exemplo: `tests/sim/scenarios/real-usage/SIM-RU-01*.yaml`.

- Topo: `id` (único), `title`, `tags` (`critical`, `calendar`...), `source`
  (`real-usage|failure|adversarial|synthetic`), `clock` (`D0 09:00`), `seed`
  (`calendar`, `tasks`, `gmail`, `calendars`, `evolution`; datas relativas `D1 10:00`,
  `D-1`), `steps`.
- Cada step tem exatamente um tipo: `telegram: "texto"`, `whatsapp_control: "texto"`,
  `whatsapp_contact: "texto"` ou `{text, jid, from_me, group, push_name}`,
  `clock: "D1 08:00"` ou `"+2h"`, `job: heartbeat|daily-summary`,
  `fault: {windmill|telegram: ...}`; mais `expect:` opcional.
- `expect`: `reply_within_s`, `max_latency_s`, `reply_matches` (regex; único check de
  texto), `no_reply` (+ `no_reply_window_s`, default 15), `calendar`
  (`created: [{summary_contains, start, end}]`, `count`), `tasks`
  (`created: [{title_contains, due}]`, `count`), `gmail` (`deleted_count`,
  `deleted_ids_include`, `not_deleted`), `tools_called_any`, `tools_not_called`,
  `outbound_to_third_parties`, `postgres` (`[{table, where, count}]`; tabelas:
  `pending_commitments`, `whatsapp_contacts`, `messages`, `session_tool_snapshots`).
  Cenários afirmam estado e efeitos, não redação.

### Critério de aprovação

`critical` e `adversarial`: N/N repetições. Demais: ≥ 2/3. Relatórios em
`logs/sim/`.

### Cassetes (replay)

Respostas do LLM gravadas em `tests/sim/cassettes/` alimentam o modo `replay` (CI,
sem chave). **Regravar após qualquer mudança de prompt, docstring de tool ou schema
de tool:** `./scripts/evi-sim run --tag critical --llm record` e commitar os
cassetes.

### Isolamento

Projeto compose `evi-sim` (portas 18000/18080), sem `.env` de produção, sem mount
de `./data` nem `./logs`, e `guard` valida o compose renderizado (projeto, env_file, binds de
`data`/`logs`, hosts reais como api.telegram.org/googleapis.com) e aborta `up`/`run`
se algo vazar. Chave do LLM: `EVI_SIM_GEMINI_API_KEY`; se ausente, cai em
`GEMINI_API_KEY` de produção com aviso — a **cota é compartilhada**. `replay` nunca
usa chave.

### Novo cenário a partir de falha real

1. Copie o `id`/pedido real (Telegram/WhatsApp) para um YAML em
   `tests/sim/scenarios/real-usage/` (ou `failure/`), tags `real-usage` (+ `critical`
   se for regressão que não pode voltar).
2. Reproduza o estado com `seed` e `clock`; asserte o efeito esperado em `expect`.
3. `./scripts/evi-sim run --id <ID> --repeat 3 --llm live` deve falhar antes do fix
   e passar depois; grave o cassete (`--llm record`) e commite.

Tiers legados (ainda válidos):

1. **Unit** — `pytest tests/unit -q` (no Docker/Ollama)
2. **Integration CLI** — `./scripts/evi-test <feature> [--verbose]`
3. **Smoke E2E** — `./scripts/evi-test smoke --full` (needs agent-api + Ollama)

## Commands

| Feature | Command | SCN |
|---------|---------|-----|
| All offline smoke | `./scripts/evi-test smoke` | SCN-E2E-02 |
| Full stack | `./scripts/evi-test smoke --full` | SCN-E2E-05 |
| Session isolation | `./scripts/evi-test sessions` | SCN-RT-03, SCN-TEST-11 |
| Container smoke (sistema montado) | `./scripts/evi-test container` | SCN-CI-02, SCN-CI-03 |
| Bounded memory (single buffer) | `./scripts/evi-test memory` | — |
| Session round-trip (Postgres) | `DATABASE_URL=... ./scripts/evi-test session` | — |
| WhatsApp pipeline | `./scripts/evi-test whatsapp --verbose` | SCN-WA-04 |
| Commitments queue | `DATABASE_URL=... ./scripts/evi-test commitments` | SCN-WA-10, SCN-CHAT-02 |
| File organizer | `./scripts/evi-test file-organizer` | SCN-FO-01 |
| Calendar (mock) | `./scripts/evi-test calendar` | SCN-CAL-02 |
| Calendar (live Windmill) | `./scripts/evi-test calendar --live-windmill` | SCN-CAL-04 |
| Tasks (mock) | `./scripts/evi-test tasks` | SCN-TASK-03 |
| Tasks (live Windmill) | `./scripts/evi-test tasks --live-windmill` | SCN-TASK-05 |
| Email (mock) | `./scripts/evi-test email` | SCN-EMAIL-04 |
| Email (live Windmill) | `./scripts/evi-test email --live-windmill` | SCN-EMAIL-05 |
| Evolution parse | `./scripts/evi-test evolution` | SCN-WA-05 |
| Telegram (polling setup) | `./scripts/evi-telegram-polling-setup.sh` | SCN-TG-03 |
| Telegram (live E2E) | `./scripts/evi-telegram-verify.sh` | SCN-TG-02, SCN-WA-12 |
| Telegram (mock) | `./scripts/evi-test telegram` | SCN-TG-01 |
| Telegram LLM audit/persist | `tests/unit/test_telegram_handler.py` | SCN-TG-02 |
| Telegram (live webhook) | `./scripts/evi-test telegram --live-telegram` | SCN-TG-02 |
| Telegram (polling) | `TELEGRAM_MODE=polling` + poller startup | SCN-TG-04 |
| Telegram (direct list) | `tests/unit/test_telegram_list.py` | SCN-TG-05 |
| Calendar list events (unit) | `tests/unit/test_telegram_list.py` | SCN-CAL-06 |
| Calendar list events (mock) | `./scripts/evi-test calendar-list` | SCN-CAL-06 |
| Calendar list events (live) | `./scripts/evi-test calendar-list --live-windmill` | SCN-CAL-06 live |
| Evolution log fields | `./scripts/evi-test evolution` | SCN-WA-13..15 |
| JSONL log retention | `agent/services/log_retention.py` | SCN-OPS-02 |
| Deep health (unit) | `tests/unit/test_health.py` | SCN-API-02 |
| Deep health (offline) | `./scripts/evi-test health` | SCN-API-02 |
| Deep health (live) | `./scripts/evi-test health --full` | SCN-API-02 live |
| Prometheus metrics | `./scripts/evi-test metrics` | SCN-OPS-03 |
| GitHub Actions CI | `.github/workflows/ci.yml` | SCN-CI-01 |
| RAG (offline) | `./scripts/evi-test rag` | SCN-RAG-01..03 wiring |
| RAG (live Qdrant) | `./scripts/evi-test rag --live-qdrant` | SCN-RAG-04 |
| LLM factory | `tests/unit/test_llm_factory.py` | EVI_LLM_PROVIDER, EVI_EMBED_PROVIDER |
| Integration factory | `tests/unit/test_integration_factory.py` | EVI_ORCHESTRATOR, EVI_WHATSAPP_PROVIDER |
| Notes | `./scripts/evi-test notes` | SCN-NOTE-02 |
| Session/Postgres | `DATABASE_URL=... ./scripts/evi-test session` | SCN-E2E-03 |
| Contact FS memory | `./scripts/evi-test contact-memory` | SCN-MEM-02 |
| Daily summary | `./scripts/evi-test daily-summary` | SCN-MEM-02b |
| Knowledge graph | `./scripts/evi-test graph` | SCN-MEM-03 |
| Memory live (stack) | `./scripts/evi-test memory-live` | SCN-MEM-02/03 live |

### Runtime v3 / Inbox UX (Jun 2026)

| Feature | Command | SCN |
|---------|---------|-----|
| Runtime v3 offline | `./scripts/evi-test runtime-v3` | SCN-UX-RUNTIME |
| Inbox UX mock | `./scripts/evi-test inbox-ux` | SCN-UX-INBOX-01/02/04 |
| Inbox UX live harness | `./scripts/evi-inbox-ux-verify.sh` | SCN-UX-INBOX live |
| Chat invoke (unit) | `tests/unit/test_chat_invoke.py` | SCN-UX-CHAT |
| LLM-first control (unit) | `tests/unit/test_whatsapp_control.py`, `test_telegram_handler.py` | SCN-UX-WA-CTRL-01 |
| Evolution require_ts | `./scripts/evi-test evolution` | SCN-UX-WA-ING-01 |
| Email messages fixture | `tests/fixtures/windmill/email_summary_messages.json` | SCN-EMAIL-04 |


| SCN | Test file |
|-----|-----------|
| SCN-CHAT-03 | `tests/unit/test_commitment_tools.py` — confirm event → `schedule_event` |
| SCN-CHAT-04 | `tests/unit/test_commitment_tools.py` — confirm task → `create_task` |
| SCN-EMAIL-03 | `tests/unit/test_email_tool.py` — `summarize_inbox` wiring |
| SCN-WA-09 | `tests/unit/test_evolution_filter.py` |
| SCN inbox priority | `tests/unit/test_commitment_priority.py` |
| SCN-WA-16 LLM fallback | `tests/unit/test_whatsapp_llm_extract.py` |
| SCN-UX-CHAT | `tests/unit/test_chat_invoke.py` — context + tool snapshots |
| SCN-UX-WA-CTRL | `tests/unit/test_whatsapp_control.py` — LLM-first when `EVI_DIRECT_HANDLERS=false` |

```bash
pytest tests/unit/test_commitment_tools.py -q
```

## WhatsApp logs

```bash
./scripts/evi-test whatsapp --verbose
jq -s '.' logs/whatsapp_*.jsonl | less
```

Golden file: `tests/golden/whatsapp_commitments.json`

Windmill offline fixtures: `tests/fixtures/windmill/` (replaces legacy `n8n/` prefix per SCN-DEP-02).

## OpenSpec verify

```bash
pytest tests/unit -q && ./scripts/evi-test smoke
openspec validate --specs
```

Scenario IDs are defined in `openspec/specs/*/spec.md`.

## E2E checklist (SCN-E2E)

| Step | Command | Pass criteria |
|------|---------|---------------|
| SCN-E2E-01 | `docker compose up -d --build` | postgres → qdrant/windmill healthy → agent-api (SCN-OPS-01) |
| SCN-OPS-01 | `docker compose ps` | postgres, qdrant, windmill-server, agent-api show `healthy` |
| SCN-E2E-02 | `./scripts/evi-test smoke` | 13/13 offline |
| SCN-E2E-03 | `export DATABASE_URL=postgresql://evi:PASS@localhost:5433/evidb` | session + commitments connect (host port 5433) |
| SCN-E2E-04 | Ollama running on host (not in compose) | `curl host.docker.internal:11434` from agent; chat retries until model loads |
| SCN-E2E-05 | `./scripts/evi-test smoke --full` | chat PASS or documented skip |
| SCN-E2E-06 | `./scripts/evi-test evolution` | parse fixture PASS |
| SCN-CHAT-02 | `DATABASE_URL=... ./scripts/evi-test commitments` | list tool returns seeded row |

### Last run

- **2026-06-05** — `evi-commitment-close-loop`: run `pytest tests/unit -q && ./scripts/evi-test smoke` after apply
- Full stack: requires Ollama + compose (see SCN-E2E-04/05)
