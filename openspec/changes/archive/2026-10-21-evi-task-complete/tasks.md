## 1. Base

- [x] 1.1 Script Windmill `complete_task` + operação `complete_task` no integration, env, README do windmill, `_TOOL_CHECK`
  - SCN-TASK-06
  - Files: `windmill/f/integrations/complete_task.py`, `windmill/f/integrations/complete_task.script.yaml`, `agent/integrations/windmill.py`, `agent/services/tool_result.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_fake_windmill.py -q`

- [x] 1.2 Tool `complete_tasks` (resolução em código, `@guarded_write`), IDs curtos em `list_tasks`, registro + `WRITE_TOOLS`
  - SCN-TASK-06, SCN-TASK-07, SCN-TASK-08
  - Files: `agent/tools/task_tool.py`, `agent/tools/registry.py`, `agent/services/write_guard.py`, `agent/services/response_format.py`, `tests/unit/test_complete_tasks.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_complete_tasks.py tests/unit/test_write_guard.py tests/unit/test_response_format.py -q`

## 2. Simulação e fechamento

- [x] 2.1 Fake Google (`PATCH` de tarefa) e fake Windmill; prompt do grafo; cenário `SIM-TASK-01`
  - SCN-TASK-06
  - Files: `agent/testing/sim/fake_google.py`, `agent/testing/sim/fake_windmill.py`, `agent/graph.py`, `tests/sim/scenarios/tasks/`, `tests/unit/test_sim_fake_windmill.py`
  - Verify: `./scripts/evi-sim run --id SIM-TASK-01 --repeat 3 --llm live`

- [x] 2.2 Revisão leve de superfície (tool de escrita nova), gates, BACKLOG + Progress
  - SCN-TASK-08
  - Files: `docs/security/threat-model.md`, `docs/security/findings.md`, `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `./scripts/evi-security-scan`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
