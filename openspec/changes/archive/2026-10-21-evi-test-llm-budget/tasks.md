## 1. Modo fill no cassete

- [x] 1.1 Provedor `sim-fill` (chat): `try_lookup` serve do cassete; chave nova ou excedente chama o modelo real e **acrescenta** a linha (append-only); `real`/`served` em `/tmp/evi-sim-cassette-stats`
  - SCN-SIM-10
  - Files: `agent/testing/sim/cassette.py`, `agent/llm.py`, `tests/unit/test_sim_cassette.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_cassette.py -q`

- [x] 1.2 Chamadas estruturadas em fill: `_sim_cassette_mode` mapeia `sim-fill`; `structured_call("fill", …)` serve ou chama e grava; falha não gravada
  - SCN-SIM-10
  - Files: `agent/services/llm_structured.py`, `agent/testing/sim/cassette.py`, `tests/unit/test_sim_cassette.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_cassette.py tests/unit/test_llm_structured.py -q`

## 2. Runner e relatório

- [x] 2.1 `--llm fill` no `scripts/evi-sim` e no runner: snapshot do cassete original por cenário no início do run, enviado em toda tentativa; tentativa aprovada salva o cassete (original + novas); `--max-llm-calls` conta só chamadas reais
  - SCN-SIM-10, SCN-SIM-11
  - Files: `scripts/evi-sim`, `agent/testing/sim/runner.py`, `tests/unit/test_sim_runner_fill.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_runner_fill.py -q`

- [x] 2.2 Relatório com chamadas reais × servidas e tokens reais, por tentativa e no total
  - SCN-SIM-11
  - Files: `agent/testing/sim/report.py`, `agent/testing/sim/runner.py`, `tests/unit/test_sim_report.py`, `tests/unit/test_token_accounting.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_report.py -q`

## 3. Cache do llm-eval

- [x] 3.1 `testing/llm_eval/cache.py` (chave por tarefa/provedor/modelos/prompt/schema, amostra i na i-ésima chamada, `data/eval/cache.jsonl`, falha fora do cache); aplicado em `run_llm_eval`; `--no-cache` / `EVI_LLM_EVAL_CACHE=0`
  - SCN-SIM-12
  - Files: `agent/testing/llm_eval/cache.py`, `agent/testing/cli.py`, `tests/unit/test_llm_eval_cache.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_llm_eval_cache.py tests/unit/test_llm_eval.py -q`

## 4. Regra de verificação e fechamento

- [x] 4.1 Trocar `--llm live` por `--llm fill` nas regras e comandos; `live` só para deriva (periódica); `llm-eval --no-cache` ao trocar modelo
  - SCN-SIM-10
  - Files: `openspec/config.yaml`, `CLAUDE.md`, `docs/testing.md`, `.claude/commands/implement-change.md`, `.claude/commands/run-queue.md`
  - Verify: `grep -n "llm fill" openspec/config.yaml CLAUDE.md docs/testing.md .claude/commands/implement-change.md .claude/commands/run-queue.md`

- [x] 4.2 Prova no sistema montado: `critical` em fill com cassetes atuais = 0 chamadas reais e cassetes idênticos; replay continua verde; gates; BACKLOG + Progress
  - SCN-SIM-10, SCN-SIM-11
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `./scripts/evi-sim run --tag critical --repeat 3 --llm fill` (real = 0), `git diff --exit-code tests/sim/cassettes`, `./scripts/evi-sim run --tag critical --llm replay`, `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
