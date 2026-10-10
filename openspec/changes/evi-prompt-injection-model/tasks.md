## 1. Garantias no código

- [x] 1.0 Telegram só aceita o chat do usuário: mensagens de texto de qualquer chat diferente de `TELEGRAM_CHAT_ID` (ou da lista `TELEGRAM_ALLOWED_CHAT_IDS`) são ignoradas sem resposta e registradas em log (hoje só a voz verifica o chat)
  - SCN-INJ-00
  - Files: `agent/services/telegram_handler.py`, `tests/unit/test_telegram_handler.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_handler.py -q` — chat desconhecido não chega ao grafo; sem `TELEGRAM_CHAT_ID` configurado, comportamento atual (aviso no log)


- [ ] 1.1 Exclusão em dois passos com token em snapshot, turno posterior e confirmação do texto do usuário; `max_messages` ≤ 50
  - SCN-INJ-01, SCN-INJ-02
  - Files: `agent/tools/email_tool.py`, `agent/services/write_guard.py`, `agent/services/turn_log.py`, `tests/unit/test_email_delete_confirm.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_email_delete_confirm.py -q`

- [ ] 1.2 Allowlist de tools de escrita por origem do turno
  - SCN-INJ-03
  - Files: `agent/services/write_guard.py`, `agent/tools/registry.py`, `tests/unit/test_write_guard.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_write_guard.py -q` — todas as tools de escrita registradas chamam a guarda

- [x] 1.3 Saídas de `summarize_inbox` e `list_calendar_events` delimitadas + `AGENTS.md`
  - SCN-INJ-04
  - Files: `agent/services/response_format.py`, `agent/tools/calendar_tool.py`, `EVI_WORKSPACE/AGENTS.md`, `tests/unit/test_response_format.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_response_format.py -q` e `./scripts/evi-test inbox-ux`

## 2. Corpus e simulação

- [ ] 2.1 `tests/fixtures/injection/` + `evi-test injection` (offline) no smoke
  - SCN-INJ-01..04
  - Files: `tests/fixtures/injection/`, `agent/testing/cli.py`, `docs/testing.md`
  - Verify: `./scripts/evi-test injection && ./scripts/evi-test smoke`

- [ ] 2.2 `SIM-ADV-04`, `SIM-ADV-05`; ajustar cenários de exclusão existentes (SIM-RU-06) ao fluxo de confirmação; regravar cassettes
  - SCN-INJ-01, SCN-INJ-02
  - Files: `tests/sim/scenarios/adversarial/`, `tests/sim/scenarios/real-usage/`, `tests/sim/cassettes/`
  - Verify: `./scripts/evi-sim run --tag adversarial,gmail --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 2.3 Sincronizar specs, `BACKLOG.md`/`Progress.md`/roadmap e arquivar
  - Files: `openspec/changes/evi-prompt-injection-model/`, `openspec/BACKLOG.md`, `Progress.md`, `openspec/specs/roadmap.md`
  - Verify: `openspec validate --specs && PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-sim run --tag critical,adversarial --repeat 3 --llm live && ./scripts/evi-sim run --tag critical --llm replay`
