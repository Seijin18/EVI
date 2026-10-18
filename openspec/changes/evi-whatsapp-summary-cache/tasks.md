## 1. Fonte local

- [x] 1.1 `message_timeline.recent_rows(days, limit)` (pastas diretas canônicas, leitura do fim para trás, dedupe de compromisso, mesmo formato de linha da Evolution)
  - SCN-WA-RECENT-01
  - Files: `agent/services/message_timeline.py`, `tests/unit/test_message_timeline.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_message_timeline.py -q`

- [x] 1.2 `whatsapp_activity` usa a fonte local; Evolution só para grupos da whitelist e lacunas, em paralelo com timeout total; flag `EVI_WHATSAPP_LOCAL_FIRST`
  - SCN-WA-RECENT-01, SCN-WA-RECENT-02
  - Files: `agent/services/whatsapp_activity.py`, `agent/services/evolution_discovery.py`, `tests/unit/test_whatsapp_activity.py`, `tests/unit/test_evolution_discovery.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_activity.py tests/unit/test_evolution_discovery.py tests/unit/test_wrap_third_party.py -q`

- [x] 1.3 Cache do resumo (TTL 10 min, chave com o último ts)
  - SCN-WA-RECENT-03
  - Files: `agent/services/whatsapp_activity.py`, `tests/unit/test_whatsapp_activity.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_activity.py -q`

## 2. Simulação e fechamento

- [x] 2.1 (id SIM-WA-04: SIM-WA-02 já existia; latência por tool não é observável na sim — usado 0 findMessages + tempo do turno) Cenário `SIM-WA-04` (resumo vem da timeline local; latência da tool < 5 s com a Evolution lenta no fake); cassetes; `docs/testing.md`
  - SCN-WA-RECENT-01
  - Files: `tests/sim/scenarios/whatsapp/`, `tests/sim/cassettes/`, `agent/testing/sim/fake_evolution.py`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --id SIM-WA-04 --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [x] 2.2 Deploy, gates, BACKLOG + Progress
  - SCN-WA-RECENT-01
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
