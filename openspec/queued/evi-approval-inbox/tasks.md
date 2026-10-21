## 1. Núcleo

- [ ] 1.1 Tabelas `proposals` e `autonomy_levels`; `proposals.py` (registro de tipos, criar, aprovar/rejeitar idempotente, expirar)
  - SCN-PROP-01, SCN-PROP-03
  - Files: `agent/db.py`, `agent/services/proposals.py`, `tests/unit/test_proposals.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_proposals.py tests/unit/test_db.py -q`

- [ ] 1.2 Telegram: mensagem por proposta, `a1:` com conferência de chat/mensagem/versão/estado, ✏️ para tipos editáveis
  - SCN-PROP-01, SCN-PROP-02
  - Files: `agent/services/telegram_handler.py`, `agent/services/proposals.py`, `tests/unit/test_telegram_handler.py`, `tests/unit/test_proposals.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_handler.py tests/unit/test_proposals.py -q`

- [ ] 1.3 Expiração no loop in-process (mensagem editada, nunca executa)
  - SCN-PROP-03
  - Files: `agent/services/reminder_loop.py`, `agent/services/proposals.py`, `tests/unit/test_reminder_loop.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reminder_loop.py tests/unit/test_proposals.py -q`

## 2. Migração e superfícies

- [ ] 2.1 Confirmações de `contact_policy` e `study` viram tipos registrados (comportamento igual; testes antigos verdes)
  - SCN-PROP-04
  - Files: `agent/services/contact_policy.py`, `agent/services/study.py`, `tests/unit/test_contact_policy.py`, `tests/unit/test_study.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_policy.py tests/unit/test_study.py -q`

- [ ] 2.2 Triagem de lacunas vira tipo `gap_triage`
  - SCN-PROP-04
  - Files: `agent/services/capability_gaps.py`, `agent/services/usage_report.py`, `tests/unit/test_capability_gaps.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_capability_gaps.py tests/unit/test_usage_report.py -q`

- [ ] 2.3 `/pendentes`, linha "🗂" no briefing, comando `autonomia`; `/ajuda`
  - SCN-PROP-05
  - Files: `agent/services/chat_commands.py`, `agent/services/briefing.py`, `tests/unit/test_chat_commands.py`, `tests/unit/test_briefing.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_chat_commands.py tests/unit/test_briefing.py -q`

- [ ] 2.4 API `GET /v1/proposals`, `POST /v1/proposals/{id}/approve|reject` (auth existente, mesma idempotência)
  - SCN-PROP-06
  - Files: `agent/main.py`, `tests/unit/test_main_endpoints.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_main_endpoints.py -q`

## 3. Segurança, simulação e fechamento

- [ ] 3.1 Revisão leve de segurança (rotas novas, callback novo, execução diferida)
  - SCN-PROP-06
  - Files: `docs/security/threat-model.md`, `docs/security/findings.md`
  - Verify: `./scripts/evi-security-scan`

- [ ] 3.2 Cenário `SIM-PROP-01` (proposta → ✅ executa uma vez; segundo toque "já feito"; outra expira sem executar)
  - SCN-PROP-01, SCN-PROP-03
  - Files: `tests/sim/scenarios/proposals/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag proposals --repeat 3 --llm fill` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.3 Gates, BACKLOG + Progress
  - SCN-PROP-01
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `./scripts/evi-sim run --tag critical --repeat 3 --llm fill`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
