## 1. Esperando sua resposta

- [x] 1.1 Tabela `wa_conversation_state` + helpers + atualização no webhook para conversas diretas (inclusive `fromMe` sem eco), antes do filtro de processamento; fixture `messages_upsert_from_me.json`
  - SCN-DEBT-01, SCN-DEBT-02
  - Files: `agent/db.py`, `agent/main.py`, `tests/unit/test_db.py`, `tests/unit/test_reply_debts.py`, `tests/fixtures/evolution/messages_upsert_from_me.json`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reply_debts.py -q` e `DATABASE_URL=<PG efêmero> EVI_TEST_EPHEMERAL_DB=1 PYTHONPATH=agent python3 -m pytest tests/unit/test_db.py -q` — grupo e chat de controle não gravam estado; `fromMe` não entra na extração

- [ ] 1.2 `services/reply_debts.py` (consulta de pendências, filtro de "ok/👍") + tools `list_reply_debts`, `dismiss_reply_debt` + registro + linha no `AGENTS.md`
  - SCN-DEBT-01, SCN-DEBT-03
  - Files: `agent/services/reply_debts.py`, `agent/tools/reply_debt_tools.py`, `agent/tools/registry.py`, `EVI_WORKSPACE/AGENTS.md`, `tests/unit/test_reply_debts.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reply_debts.py -q`

## 2. Promessas, combinados e briefing

- [ ] 2.1 Heurística de promessas sobre `fromMe` diretas → `pending_commitments` `type='promise'` (só com a flag)
  - SCN-DEBT-04
  - Files: `agent/services/promises.py`, `agent/main.py`, `tests/unit/test_promises.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promises.py -q` — lista de padrões com positivos e negativos reais anonimizados

- [ ] 2.2 Combinados só com data: itens sem data → `undated` com a flag; listagens mostram só `pending`
  - SCN-DEBT-05
  - Files: `agent/services/whatsapp_processor.py`, `agent/db.py`, `tests/unit/test_whatsapp_processor.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_processor.py -q` e `./scripts/evi-test whatsapp`

- [ ] 2.3 Briefing com três subseções + fim da notificação avulsa com a flag
  - SCN-DEBT-06, SCN-DEBT-07
  - Files: `agent/services/briefing.py`, `agent/services/commitment_capture_notify.py`, `agent/services/commitment_review/deliver.py`, `tests/unit/test_briefing.py`, `tests/unit/test_commitment_capture_notify.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py tests/unit/test_commitment_capture_notify.py tests/unit/test_commitment_review_digest.py -q` e `./scripts/evi-test briefing`

- [ ] 2.4 Taxa de ação por tipo no relatório semanal
  - SCN-DEBT-08
  - Files: `agent/services/usage_report.py`, `tests/unit/test_usage_report.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_usage_report.py -q`

## 3. Simulação e fechamento

- [ ] 3.1 Cenários `SIM-DEBT-*` (contato espera resposta → aparece no briefing; usuário responde pelo celular → some; "ok" não vira pendência; promessa "te mando amanhã" → item; combinado sem data não aparece; "respondido" pelo Telegram) + `sim.env` + `.env.example` + `docs/testing.md`; regravar cassettes
  - SCN-DEBT-01..07
  - Files: `tests/sim/scenarios/reply-debts/`, `tests/sim/sim.env`, `.env.example`, `docs/testing.md`, `tests/sim/cassettes/`
  - Verify: `./scripts/evi-sim run --tag reply-debts --repeat 3 --llm live` (3/3) e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.2 Sincronizar specs com o as-built, atualizar `BACKLOG.md`/`Progress.md`/roadmap e arquivar
  - Files: `openspec/changes/evi-reply-debts/`, `openspec/BACKLOG.md`, `Progress.md`, `openspec/specs/roadmap.md`
  - Verify: `openspec validate --specs && PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-sim run --tag critical --repeat 3 --llm live && ./scripts/evi-sim run --tag critical --llm replay`
