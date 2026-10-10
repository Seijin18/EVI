## 1. Guarda de injeção (antes de qualquer conteúdo novo chegar à sessão)

- [x] 1.1 `wrap_external(text, source)` com neutralização dos marcadores e truncamento
  - SCN-SEC-01
  - Files: `agent/services/untrusted.py`, `tests/unit/test_untrusted.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_untrusted.py -q`

- [ ] 1.2 Aplicar nos três caminhos existentes + instrução defensiva no bootstrap
  - SCN-SEC-02
  - Files: `agent/services/context_assembly.py`, `agent/services/whatsapp_activity.py`, `agent/services/whatsapp_llm_extract.py`, `EVI_WORKSPACE/AGENTS.md`, `tests/unit/test_whatsapp_activity.py` (novo)
  - Verify: `PYTHONPATH=agent python3 -m pytest -q tests/unit/test_context_assembly.py tests/unit/test_whatsapp_llm_extract.py tests/unit/test_llm_extract.py tests/unit/test_whatsapp_activity.py` e `./scripts/evi-test runtime-v3`; o bootstrap mudou → regravar cassettes (`./scripts/evi-sim run --tag critical --llm record`) e `./scripts/evi-sim run --tag adversarial --repeat 3 --llm live` 3/3

## 2. Briefing

- [x] 2.1 Tabela `briefing_log` + `record_briefing` / `briefing_sent_today`
  - SCN-BRIEF-04
  - Files: `agent/db.py`, `tests/unit/test_db.py`
  - Verify: `DATABASE_URL=<PG efêmero> EVI_TEST_EPHEMERAL_DB=1 PYTHONPATH=agent python3 -m pytest tests/unit/test_db.py -q` (marcador `ephemeral_db`; segunda migração idempotente; `UNIQUE(day, kind)`)

- [ ] 2.2 Coleta isolada das 4 fontes (`Section`/`BriefItem`) com erro por seção
  - SCN-BRIEF-02
  - Files: `agent/services/briefing.py`, `tests/unit/test_briefing.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py -q` — Gmail com OAuth expirado gera seção com `error` e as outras 3 seções intactas

- [ ] 2.3 Heurística de e-mail; `labelIds` no retorno do `summarize_inbox` se ausente
  - SCN-BRIEF-03
  - Files: `agent/services/briefing.py`, `windmill/f/integrations/summarize_inbox.py`, `tests/unit/test_briefing.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py -q -k email` — promoção e `noreply` descartados; sem `labelIds`, só o filtro de remetente

- [ ] 2.4 Formatação: numeração contínua, limites por seção, "+N", dia livre, campos de terceiros via `wrap_external`
  - SCN-BRIEF-01, SCN-SEC-01
  - Files: `agent/services/briefing.py`, `tests/unit/test_briefing.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py -q -k format`

- [ ] 2.5 Entrega: Telegram + memória da sessão + snapshot `morning_briefing` + `briefing_log` + métricas (`evi_briefing_sent_total`, `evi_briefing_replied_total`)
  - SCN-BRIEF-05, SCN-BRIEF-08
  - Files: `agent/services/briefing.py`, `tests/unit/test_briefing.py`, `agent/services/metrics.py`, `tests/unit/test_metrics.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py tests/unit/test_metrics.py -q` — snapshot contém `{n, ref}` para cada item; falha de envio grava `ok=false` e permite reenvio; resposta na sessão em até 3 h incrementa `replied`

- [ ] 2.6 `POST /jobs/briefing` (`kind`, `force`, auth, `disabled`, idempotência)
  - SCN-BRIEF-04, SCN-AUTH-02
  - Files: `agent/main.py`, `tests/unit/test_main_endpoints.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_main_endpoints.py -q` — sem API key → 401; segundo POST no mesmo dia → `already_sent`

- [ ] 2.7 Script Windmill `briefing` + doc do schedule
  - SCN-BRIEF-06
  - Files: `windmill/f/integrations/briefing.py`, `windmill/f/integrations/briefing.script.yaml`, `windmill/README.md`
  - Verify: `python3 -c "import ast;ast.parse(open('windmill/f/integrations/briefing.py').read())"` e teste unitário do script contra um servidor fake; a execução real no Windmill (conta real) fica como pendência do usuário — a entrega ponta a ponta é verificada na simulação (3.1)

- [x] 2.8 Heartbeat silencia manutenção quando o briefing está ligado
  - SCN-BRIEF-07
  - Files: `agent/services/heartbeat.py`, `tests/unit/test_heartbeat.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_heartbeat.py -q`

## 3. Harness

- [ ] 3.1 `evi-test briefing` (offline) + cenários de simulação (`SIM-BRIEF-*`: dia normal, Gmail com OAuth expirado, e-mail adversarial, "confirma 2" após o briefing) + `.env.example`
  - SCN-BRIEF-01..05, SCN-SIM-08
  - Files: `agent/testing/cli.py`, `tests/sim/scenarios/briefing/`, `.env.example`, `docs/testing.md`
  - Verify: `./scripts/evi-test briefing && ./scripts/evi-test smoke && ./scripts/evi-sim run --tag briefing --repeat 3 --llm live` (smoke passa a 14/14; `SIM-BRIEF-*` 3/3)


- [ ] 3.2 Sincronizar specs com o as-built, atualizar contagens (10 specs, smoke 14/14) em `CLAUDE.md`/`Progress.md`/`BACKLOG.md`, `openspec archive`
  - Files: `openspec/changes/evi-morning-briefing/specs/`, `CLAUDE.md`, `Progress.md`, `openspec/BACKLOG.md`
  - Verify: `openspec validate --specs && PYTHONPATH=agent python3 -m pytest tests/unit -q && ruff check agent/ --select E,W,F --ignore E501`
