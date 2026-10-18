## 1. Estado das fontes

- [x] 1.1 `EvolutionClient.connection_state()`; check `whatsapp` no `/health` (não fatal); tabela `source_status` + helpers (`record_source`, `list_sources_down`)
  - SCN-REL-04
  - Files: `agent/messaging/evolution.py`, `agent/services/health.py`, `agent/db.py`, `tests/unit/test_health.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_health.py tests/unit/test_db.py -q`

- [x] 1.2 Sonda: check `whatsapp` (`disconnected`/`upstream_error`), grava `source_status`; texto do OAuth com o ciclo de 7 dias e a saída definitiva; flag `EVI_SOURCE_ALERTS_ENABLED`
  - SCN-USE-06, SCN-USE-09
  - Files: `agent/services/probe.py`, `tests/unit/test_probe.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_probe.py -q`

## 2. Watchdog

- [x] 2.1 Watchdog verifica o WhatsApp direto na Evolution: aviso após 2 leituras fora de `open`, um por queda, aviso de volta; estado próprio no arquivo; lê só as chaves necessárias do `.env`
  - SCN-REL-03
  - Files: `scripts/evi-watchdog`, `tests/unit/test_watchdog.py`, `docs/operations.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_watchdog.py -q`

## 3. Briefing

- [x] 3.1 Selo de fontes fora no topo do briefing (agrupa Google; WhatsApp com desde quando), não colapsável, sem repetir o motivo na seção
  - SCN-BRIEF-02, SCN-BRIEF-05
  - Files: `agent/services/briefing.py`, `tests/unit/test_briefing.py`, `tests/fixtures/briefing/`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py -q` e `./scripts/evi-test briefing`

## 4. Simulação e fechamento

- [ ] 4.1 Fake Evolution responde `connectionState` (estado semeável); cenário `SIM-REL-05` (WhatsApp `close` → briefing com selo; sonda avisa uma vez); cassetes; `docs/testing.md`
  - SCN-BRIEF-05, SCN-USE-09
  - Files: `agent/testing/sim/fake_evolution.py`, `tests/sim/scenarios/reliability/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag reliability --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 4.2 Deploy (rebuild do agent-api; watchdog atualizado é o mesmo arquivo do timer), gates, BACKLOG + Progress
  - SCN-REL-03
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
