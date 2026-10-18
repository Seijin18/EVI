## 1. Dicas

- [x] 1.1 `discovery_tips` (catálogo, detecção de uso no `turn_log` em 14 dias, rotação diária) + linha no rodapé do briefing da manhã respeitando o teto; flag `EVI_BRIEFING_TIPS`
  - SCN-TIP-01, SCN-TIP-02
  - Files: `agent/services/discovery_tips.py`, `agent/services/briefing.py`, `agent/db.py`, `tests/unit/test_discovery_tips.py`, `tests/unit/test_briefing.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_discovery_tips.py tests/unit/test_briefing.py -q`

## 2. Prévia da noite

- [x] 2.1 Ação "lembrar amanhã 9h" nos itens com prazo amanhã da prévia da noite (botão `rm` + resposta "lembra N"), criando o lembrete pelo código de `create_reminder`
  - SCN-TIP-03
  - Files: `agent/services/briefing.py`, `agent/services/telegram_handler.py`, `agent/tools/reminder_tools.py`, `tests/unit/test_briefing.py`, `tests/unit/test_telegram_handler.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py tests/unit/test_telegram_handler.py -q`

- [x] 2.2 Schedule `briefing_evening` (21:00, ligado) no repo + `windmill/README.md`; publicar com push restrito (`wmill sync push --includes`)
  - SCN-TIP-04
  - Files: `windmill/f/integrations/briefing_evening.schedule.yaml`, `windmill/README.md`
  - Verify: `wmill schedule list --workspace evi` mostra `briefing_evening` habilitado

## 3. Simulação e fechamento

- [x] 3.1 Cenários `SIM-TIP-01` (dica de lembrete aparece; some depois de criar um lembrete) e `SIM-TIP-02` (prévia da noite → toque "lembrar amanhã" → lembrete criado); cassetes; `docs/testing.md`
  - SCN-TIP-01, SCN-TIP-03
  - Files: `tests/sim/scenarios/briefing/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag briefing --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [x] 3.2 Deploy, gates, BACKLOG + Progress
  - SCN-TIP-04
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
