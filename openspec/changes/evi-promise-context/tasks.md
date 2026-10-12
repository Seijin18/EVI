## 1. Correções já aplicadas (sincronizar)

- [x] 1.1 Canais `@newsletter`/`@broadcast` fora das dívidas de resposta (`fd8d631`)
  - SCN-DEBT-09
  - Files: `agent/services/reply_debts.py`, `tests/unit/test_reply_debts.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reply_debts.py -q`

- [x] 1.2 Dedupe por id em `parse_evolution_message_list` (`b6148ca`)
  - SCN-WA-DEDUP-01
  - Files: `agent/services/evolution_parser.py`, `tests/unit/test_whatsapp_backfill.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_backfill.py -q`

## 2. Avaliação com contexto

- [ ] 2.1 `promise_context.conversation_context(jid, before_ts, knowledge="")`: até 10 mensagens / 24 h via `findMessages` (dois lados, `wrap_external`, nome do registro), fallback `read_timeline_tail`; `knowledge` vazio nesta versão
  - SCN-DEBT-10
  - Files: `agent/services/promise_context.py`, `tests/unit/test_promise_context.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promise_context.py -q`

- [ ] 2.2 `evaluate_promise(msg, context, invoke=None)`: prompt + parse JSON; `what` vazio/genérico = não; falha = `None`
  - SCN-DEBT-10, SCN-DEBT-11, SCN-DEBT-12
  - Files: `agent/services/promise_context.py`, `tests/unit/test_promise_context.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promise_context.py -q`

- [ ] 2.3 `capture_promises` agenda a avaliação em `run_in_background`; grava só se confirmada (título/data do LLM) ou por padrão se falhar/flag off; `EVI_PROMISE_CONTEXT_ENABLED` no `.env.example`
  - SCN-DEBT-04, SCN-DEBT-10, SCN-DEBT-11, SCN-DEBT-12
  - Files: `agent/services/promises.py`, `agent/main.py`, `tests/unit/test_promises.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promises.py tests/unit/test_reply_debts.py -q` e `./scripts/evi-test smoke`

- [ ] 2.4 `reevaluate_pending_promises()` + comando `./scripts/evi-test promise-reeval` (dry-run por padrão, `--apply` grava)
  - SCN-DEBT-13
  - Files: `agent/services/promise_context.py`, `agent/testing/cli.py`, `tests/unit/test_promise_context.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_promise_context.py -q`

## 3. Simulação e fechamento

- [ ] 3.1 Cenários `SIM-DEBT-07` ("Pode deixar" após pedido → promessa com objeto) e `SIM-DEBT-08` ("Pode deixar" após agradecimento → nada); regravar cassettes; `docs/testing.md`
  - SCN-DEBT-10, SCN-DEBT-11
  - Files: `tests/sim/scenarios/reply-debts/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag reply-debts --repeat 3 --llm live` (3/3) e `./scripts/evi-sim run --tag critical --repeat 3 --llm live`

- [ ] 3.2 Rodar a reavaliação nas promessas atuais (dry-run → revisar com o usuário → `--apply`); gates finais
  - SCN-DEBT-13
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
