## 1. Base

- [x] 1.1 Tabela `scheduled_tasks` + serviço (`create/list/cancel/pause`, próxima ocorrência pelos presets dos lembretes, tetos 10 ativas / 6 execuções por dia)
  - SCN-SCHED-01, SCN-SCHED-04
  - Files: `agent/services/scheduled_tasks.py`, `agent/db.py`, `tests/unit/test_scheduled_tasks.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_scheduled_tasks.py tests/unit/test_db.py -q`

- [x] 1.2 Tools de agendamento (`@guarded_write`, só por pedido explícito) registradas no `registry`
  - SCN-SCHED-01
  - Files: `agent/tools/scheduled_task_tools.py`, `agent/tools/registry.py`, `tests/unit/test_scheduled_task_tools.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_scheduled_task_tools.py tests/unit/test_write_guard.py -q`

## 2. Execução

- [x] 2.1 Grafo com lista de tools filtrada (`read_only_tools()`), turno `channel='scheduled'` com sessão própria; guarda por origem recusa escrita nesse canal
  - SCN-SCHED-02, SCN-SCHED-03
  - Files: `agent/graph.py`, `agent/main.py`, `agent/services/scheduled_tasks.py`, `tests/unit/test_scheduled_tasks.py`, `tests/unit/test_write_guard.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_scheduled_tasks.py tests/unit/test_write_guard.py -q`

- [x] 2.2 Loop dispara tarefas vencidas em executor próprio (timeout 90 s), entrega no Telegram, trata falha/teto, flag `EVI_SCHEDULED_TASKS_ENABLED`
  - SCN-SCHED-02, SCN-SCHED-04
  - Files: `agent/services/reminder_loop.py`, `agent/services/scheduled_tasks.py`, `tests/unit/test_reminder_loop.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reminder_loop.py tests/unit/test_scheduled_tasks.py -q`

## 3. Simulação e fechamento

- [x] 3.1 Cenários `SIM-SCHED-01` (pedido "toda sexta 18h resuma meus e-mails" → tarefa → relógio avança → resumo entregue) e `SIM-SCHED-02` (tarefa "apague meus e-mails de promoção" → nada apagado); cassetes; `docs/testing.md`
  - SCN-SCHED-01, SCN-SCHED-03
  - Files: `tests/sim/scenarios/scheduled/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag scheduled --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [x] 3.2 Deploy, gates, BACKLOG + Progress
  - SCN-SCHED-02
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `./scripts/evi-test injection`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
