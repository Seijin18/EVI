## 1. Armazenamento e disparo

- [x] 1.1 Tabela `reminders` + helpers (`create`, `list`, `claim_due` atômico, `finish_fired`, `release`, `snooze`, `complete`, `cancel`, `requeue_stuck`)
  - SCN-REM-02, SCN-REM-03
  - Files: `agent/requirements.txt`, `agent/db.py`, `tests/unit/test_db.py`
  - Verify: `DATABASE_URL=<PG efêmero> EVI_TEST_EPHEMERAL_DB=1 PYTHONPATH=agent python3 -m pytest tests/unit/test_db.py -q` — duas chamadas concorrentes de `claim_due` não devolvem o mesmo id; migração idempotente

- [x] 1.2 `services/reminders.py`: validação, próxima ocorrência por preset (hora de parede em `EVI_TIMEZONE`, fim de mês), formatação (marca "atrasado"), `fire_due(now)` (claim → envio → histórico/snapshot → `sent`/reagenda/libera)
  - SCN-REM-02, SCN-REM-03, SCN-REM-04, SCN-REM-05
  - Files: `agent/services/reminders.py`, `tests/unit/test_reminders.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reminders.py -q` — recorrente atrasado 3 dias dispara uma vez e avança; falha de envio volta a `pending`; DST/fim de mês

- [ ] 1.3 Loop in-process (thread daemon, tick, flag, `soft_fail`) iniciado e parado no `lifespan`
  - SCN-REM-01
  - Files: `agent/services/reminder_loop.py`, `agent/main.py`, `tests/unit/test_reminder_loop.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reminder_loop.py tests/unit/test_main_endpoints.py -q` — com a flag desligada nenhuma thread sobe; start idempotente; exceção no tick não mata o loop

## 2. Tools e medida

- [ ] 2.1 Tools `create_reminder`, `list_reminders`, `cancel_reminder`, `snooze_reminder`, `complete_reminder` + registro + regras no `AGENTS.md`
  - SCN-REM-01, SCN-REM-04
  - Files: `agent/tools/reminder_tools.py`, `agent/tools/registry.py`, `EVI_WORKSPACE/AGENTS.md`, `tests/unit/test_reminder_tools.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reminder_tools.py -q` (inclui teste de que `get_all_tools()` expõe as 5 tools) — data no passado e `repeat` inválido recusados com mensagem clara; flag desligada não grava

- [ ] 2.2 Métricas (`evi_reminders_fired_total{late}`, `evi_reminder_drift_seconds`) + seção "Lembretes" no relatório semanal
  - SCN-REM-06
  - Files: `agent/services/metrics.py`, `agent/services/usage_report.py`, `tests/unit/test_metrics.py`, `tests/unit/test_usage_report.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_metrics.py tests/unit/test_usage_report.py -q`

## 3. Simulação e fechamento

- [ ] 3.1 Cenários `SIM-REM-*` (criar e disparar no horário, "adia 1h", diário, atrasado após salto de relógio, "feito") + `sim.env` + `.env.example` + `docs/testing.md`; regravar cassettes se o prompt mudou
  - SCN-REM-01..05
  - Files: `tests/sim/scenarios/reminders/`, `tests/sim/sim.env`, `.env.example`, `docs/testing.md`, `tests/sim/cassettes/`
  - Verify: `./scripts/evi-sim run --tag reminders --repeat 3 --llm live` (3/3) e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.2 Sincronizar specs com o as-built, atualizar `BACKLOG.md`/`Progress.md`/roadmap e arquivar
  - Files: `openspec/changes/evi-reminders/`, `openspec/BACKLOG.md`, `Progress.md`, `openspec/specs/roadmap.md`
  - Verify: `openspec validate --specs && PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-sim run --tag critical --repeat 3 --llm live && ./scripts/evi-sim run --tag critical --llm replay`
