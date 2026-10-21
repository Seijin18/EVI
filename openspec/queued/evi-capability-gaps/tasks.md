## 1. Registro

- [ ] 1.1 Tabela `capability_gaps` + `capability_gaps.py` (normalização, dedupe Jaccard, `policy_refused`, anonimização, espelho em `EVI_WORKSPACE/gaps/`)
  - SCN-GAP-01, SCN-GAP-03
  - Files: `agent/db.py`, `agent/services/capability_gaps.py`, `tests/unit/test_capability_gaps.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_capability_gaps.py tests/unit/test_db.py -q`

- [ ] 1.2 Tool `report_capability_gap` registrada; allowlist por origem (usuário/agendado sim, conteúdo externo não); regra no `SYSTEM_PROMPT`
  - SCN-GAP-01, SCN-GAP-02
  - Files: `agent/tools/gap_tool.py`, `agent/tools/registry.py`, `agent/services/write_guard.py`, `agent/graph.py`, `tests/unit/test_write_guard.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_write_guard.py tests/unit/test_capability_gaps.py -q`

- [ ] 1.3 Candidatos implícitos a partir de `usage_signals` (`cant_do`, 👎 + tool_failed, sem a tool no turno)
  - SCN-GAP-04
  - Files: `agent/services/usage_signals.py`, `agent/services/capability_gaps.py`, `tests/unit/test_usage_signals.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_usage_signals.py tests/unit/test_capability_gaps.py -q`

## 2. Relatório, comandos e exportação

- [ ] 2.1 Seção "🧩" no relatório semanal com ⭐/✖ (`g1:`); `/melhorias`, "importante N", "descarta N"; `/ajuda`
  - SCN-GAP-04, SCN-GAP-05
  - Files: `agent/services/usage_report.py`, `agent/services/telegram_handler.py`, `agent/services/chat_commands.py`, `tests/unit/test_usage_report.py`, `tests/unit/test_telegram_handler.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_usage_report.py tests/unit/test_telegram_handler.py -q`

- [ ] 2.2 `evi-test gaps-export <id>` → `openspec/proposals-inbox/<slug>/proposal.md` (evidência anonimizada; status `exported`); README da pasta
  - SCN-GAP-06
  - Files: `agent/testing/cli.py`, `agent/services/capability_gaps.py`, `openspec/proposals-inbox/README.md`, `tests/unit/test_capability_gaps.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_capability_gaps.py -q`

## 3. Simulação e fechamento

- [ ] 3.1 Revisão leve de segurança (tool nova; arquivos em `EVI_WORKSPACE/gaps/`; exportação para o repo)
  - SCN-GAP-02
  - Files: `docs/security/threat-model.md`, `docs/security/findings.md`
  - Verify: `./scripts/evi-security-scan`

- [ ] 3.2 Cenários `SIM-GAP-01` (pedido sem tool → registra e responde honesto, sem restrição inventada) e `SIM-GAP-02` (e-mail pedindo para registrar lacuna → nada registrado)
  - SCN-GAP-01, SCN-GAP-02
  - Files: `tests/sim/scenarios/gaps/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag gaps --repeat 3 --llm fill` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.3 Gates (cassetes `critical` regravados pelo `fill`: o prompt mudou), BACKLOG + Progress
  - SCN-GAP-01
  - Files: `openspec/BACKLOG.md`, `Progress.md`, `tests/sim/cassettes/`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `./scripts/evi-sim run --tag critical --repeat 3 --llm fill`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
