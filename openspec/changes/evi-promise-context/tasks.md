## 1. Correções já aplicadas (sincronizar)

- [x] 1.1 Canais `@newsletter`/`@broadcast` fora das dívidas de resposta (`fd8d631`)
  - SCN-DEBT-09
  - Files: `agent/services/reply_debts.py`, `tests/unit/test_reply_debts.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reply_debts.py -q`

- [x] 1.2 Dedupe por id em `parse_evolution_message_list` (`b6148ca`)
  - SCN-WA-DEDUP-01
  - Files: `agent/services/evolution_parser.py`, `tests/unit/test_whatsapp_backfill.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_backfill.py -q`

## 2. Base: tarefa estruturada, datas e avaliador

- [ ] 2.0 Avaliador `agent/testing/llm_eval/` + `./scripts/evi-test llm-eval promise` e `llm-eval-collect promise`; casos simulados em `tests/eval/promise_cases.yaml` (portar os 30 da avaliação prévia); reais em `data/eval/` (gitignored); Gemini nunca recebe reais
  - SCN-DEBT-10, SCN-DEBT-11
  - Files: `agent/testing/llm_eval/__init__.py`, `agent/testing/llm_eval/promise.py`, `agent/testing/cli.py`, `tests/eval/promise_cases.yaml`, `tests/unit/test_llm_eval.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_llm_eval.py -q` e `./scripts/evi-test llm-eval promise --cases synthetic`

- [ ] 2.1 `llm_structured.run_structured(task, prompt, schema)`: Ollama `format`/`think`, Gemini `responseSchema`/`propertyOrdering`, validação, `None` em falha, fallback só por opt-in; variáveis no `.env.example`
  - SCN-LLM-TASK-01, SCN-LLM-TASK-02
  - Files: `agent/services/llm_structured.py`, `tests/unit/test_llm_structured.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_llm_structured.py -q`

- [x] 2.2 `resolve_due(expr, ref)`: "dia 20", "fim de semana", "semana que vem", "às 19h" (hoje), além do que `_resolve_date` já cobre
  - SCN-DEBT-04, SCN-DEBT-14
  - Files: `agent/services/whatsapp_processor.py`, `tests/unit/test_whatsapp_processor.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_processor.py -q`

## 3. Avaliação com contexto

- [x] 3.1 `promise_context.conversation_context(jid, at_ts, knowledge="")` (antes 24 h/10 msgs + depois, dois lados, `wrap_external`, nome do registro; fallback timeline) e `evaluate_promise(...)` com o prompt v3 da avaliação prévia
  - SCN-DEBT-10, SCN-DEBT-11, SCN-DEBT-15
  - Files: `agent/services/promise_context.py`, `tests/unit/test_promise_context.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promise_context.py -q` e `./scripts/evi-test llm-eval promise` ≥ limiar do design

- [ ] 3.2 `capture_promises` grava `needs_eval`; loop in-process avalia após `EVI_PROMISE_EVAL_DELAY_MIN`; retry 30 min; 48 h → `pending` com texto original; listagens ignoram `needs_eval`
  - SCN-DEBT-04, SCN-DEBT-12, SCN-DEBT-15
  - Files: `agent/services/promises.py`, `agent/services/promise_context.py`, `agent/db.py`, `tests/unit/test_promises.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promises.py tests/unit/test_reply_debts.py -q` e `./scripts/evi-test smoke`

- [ ] 3.3 Varredura diária de cumprimento (promessas `pending` com mensagens novas do usuário → `done`)
  - SCN-DEBT-16
  - Files: `agent/services/promise_context.py`, `agent/services/reminder_loop.py`, `tests/unit/test_promise_context.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promise_context.py -q`

- [ ] 3.4 `reevaluate_pending_promises()` + `./scripts/evi-test promise-reeval` (dry-run; `--apply`)
  - SCN-DEBT-13
  - Files: `agent/services/promise_context.py`, `agent/testing/cli.py`, `tests/unit/test_promise_context.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promise_context.py -q`

## 4. Simulação e fechamento

- [ ] 4.1 Cenários `SIM-DEBT-07` (pedido + "Pode deixar" → promessa com objeto e data), `SIM-DEBT-08` (agradecimento + "Pode deixar" → nada), `SIM-DEBT-09` (prometeu e mandou 5 min depois → nada); cassettes; `docs/testing.md`
  - SCN-DEBT-10, SCN-DEBT-11, SCN-DEBT-15
  - Files: `tests/sim/scenarios/reply-debts/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag reply-debts --repeat 3 --llm live` (3/3) e `./scripts/evi-sim run --tag critical --repeat 3 --llm live`

- [ ] 4.2 Reavaliação das promessas atuais (dry-run → revisar com o usuário → `--apply`); gates finais; BACKLOG + Progress
  - SCN-DEBT-13
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
