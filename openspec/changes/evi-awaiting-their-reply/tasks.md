## 1. Detecção

- [ ] 1.1 `awaiting_reply.candidates(now)`: estado + última mensagem `[eu]` da timeline + heurística de pedido; tabela `awaiting_dismissed`
  - SCN-AWAIT-01, SCN-AWAIT-02
  - Files: `agent/services/awaiting_reply.py`, `agent/db.py`, `tests/unit/test_awaiting_reply.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_awaiting_reply.py tests/unit/test_db.py -q`

## 2. Briefing e ações

- [ ] 2.1 Seção semanal "Esperando resposta deles" no briefing de segunda (até 3, ref `awaiting:<jid>`, botões ✖/🔔); ações por toque e por texto ("ignora N", "lembra N"); flag `EVI_AWAITING_ENABLED`
  - SCN-AWAIT-03, SCN-AWAIT-04
  - Files: `agent/services/briefing.py`, `agent/services/telegram_handler.py`, `tests/unit/test_briefing.py`, `tests/unit/test_telegram_handler.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py tests/unit/test_telegram_handler.py -q` e `./scripts/evi-test briefing`

## 3. Simulação e fechamento

- [ ] 3.1 Cenário `SIM-AWAIT-01` (você perguntou há 4 dias, sem resposta → aparece na segunda; ✖ → some; mensagem nova sua → volta); cassetes; `docs/testing.md`
  - SCN-AWAIT-03, SCN-AWAIT-04
  - Files: `tests/sim/scenarios/reply-debts/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --id SIM-AWAIT-01 --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.2 Deploy, gates, BACKLOG + Progress
  - SCN-AWAIT-01
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
