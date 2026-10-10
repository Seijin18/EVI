## 1. Fora do ar

- [x] 1.1 `scripts/evi-watchdog` + units systemd de usuário + `--dry-run` + testes com servidor falso
  - SCN-REL-01
  - Files: `scripts/evi-watchdog`, `scripts/systemd/evi-watchdog.service`, `scripts/systemd/evi-watchdog.timer`, `tests/unit/test_watchdog.py`, `docs/operations.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_watchdog.py -q` — 1 falha não alerta, 2 alertam uma vez, volta avisa uma vez

## 2. No turno

- [x] 2.1 `/ajuda` determinístico (features ligadas) + "o que você pode fazer" sem LLM + `AGENTS.md`
  - SCN-REL-02
  - Files: `agent/services/help_text.py`, `agent/services/chat_commands.py`, `EVI_WORKSPACE/AGENTS.md`, `tests/unit/test_chat_commands.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_chat_commands.py -q`

- [x] 2.2 Ack de tool lenta (`EVI_SLOW_ACK_SEC`) pelo canal do turno, uma vez por turno
  - SCN-REL-03
  - Files: `agent/services/slow_ack.py`, `agent/services/turn_log.py`, `tests/unit/test_slow_ack.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_slow_ack.py tests/unit/test_turn_log.py -q`

- [x] 2.3 Aviso de OAuth no turno com o controle diário da sonda
  - SCN-REL-04
  - Files: `agent/services/tool_result.py`, `agent/services/probe.py`, `tests/unit/test_probe.py`, `tests/unit/test_tool_result.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_probe.py tests/unit/test_tool_result.py -q`

## 3. Simulação e fechamento

- [x] 3.1 Cenários `SIM-REL-*` (`/ajuda`; Windmill lento → "⏳" antes do resultado; OAuth expirado → aviso uma vez no dia) + `sim.env` + `.env.example`
  - SCN-REL-02..04
  - Files: `tests/sim/scenarios/reliability/`, `tests/sim/sim.env`, `.env.example`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag reliability --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.2 Sincronizar specs, `BACKLOG.md`/`Progress.md`/roadmap e arquivar
  - Files: `openspec/changes/evi-perceived-reliability/`, `openspec/BACKLOG.md`, `Progress.md`, `openspec/specs/roadmap.md`
  - Verify: `openspec validate --specs && PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-sim run --tag critical,adversarial --repeat 3 --llm live && ./scripts/evi-sim run --tag critical --llm replay`
