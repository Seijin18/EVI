## 1. Registro

- [x] 1.1 Tabela `turn_log` + `probe_log` + funções de gravação/consulta
  - SCN-USE-01
  - Files: `agent/db.py`, `tests/unit/test_db.py`
  - Verify: `DATABASE_URL=postgresql://postgres:t@127.0.0.1:55432/postgres PYTHONPATH=agent python3 -m pytest tests/unit/test_db.py -q` com PG efêmero (`docker run --rm -d --name evi-unit-pg -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=t postgres:15-alpine`; sem `DATABASE_URL` o teste é pulado); migração idempotente

- [ ] 1.2 Coletor por turno (`ContextVar`) alimentado por `parse_windmill_result` + gravação no handler de `/chat` em `soft_fail`
  - SCN-USE-01
  - Files: `agent/services/turn_log.py`, `agent/services/tool_result.py`, `agent/main.py`, `tests/unit/test_turn_log.py`, `tests/sim/scenarios/usage/SIM-USE-01.yaml`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_turn_log.py tests/unit/test_tool_result.py tests/unit/test_main_endpoints.py -q` — tool Windmill que falha grava `ok=false, reason`; erro no log não derruba o turno; `./scripts/evi-sim run --id SIM-USE-01 --repeat 3 --llm live` (Telegram + controle WhatsApp gravam `turn_log`; OAuth expirado em `schedule_event` → `reason=oauth`; `turn_log` entra na allowlist de `postgres:` do schema)

- [ ] 1.3 `is_test` (prefixos + `X-Evi-Test`) nos harnesses e `scripts/evi-cleanup-test-data` (dry-run por padrão)
  - SCN-USE-02
  - Files: `agent/services/turn_log.py`, `agent/testing/cli.py`, `scripts/evi-cleanup-test-data`, `scripts/evi-telegram-verify.sh`
  - Verify: `./scripts/evi-test smoke` grava turnos com `is_test=true`; `scripts/evi-cleanup-test-data` lista as 3 linhas "Teste digest Telegram" sem apagar

## 2. Sinais e relatório

- [ ] 2.1 `/bom` e `/ruim [motivo]` sobre o último turno da sessão
  - SCN-USE-03
  - Files: `agent/services/chat_commands.py`, `tests/unit/test_chat_commands.py`, `tests/sim/scenarios/usage/SIM-USE-02.yaml`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_chat_commands.py -q` e `./scripts/evi-sim run --id SIM-USE-02 --repeat 3 --llm live` (`/ruim marcou o dia errado` pelo Telegram marca o turno anterior)

- [x] 2.2 Sinais implícitos (correção, reformulação, tool_failed, cant_do) — job noturno idempotente
  - SCN-USE-04
  - Files: `agent/services/usage_signals.py`, `tests/unit/test_usage_signals.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_usage_signals.py -q` — inclui os pares reais "Você consegue listar meus compromissos?" → "Listar compromissos" (reformulação) e "Esse número na verdade é de…" (correção)

- [ ] 2.3 KPIs + relatório semanal (Markdown + resumo Telegram) + `/jobs/usage-report` + script Windmill
  - SCN-USE-05
  - Files: `agent/services/usage_report.py`, `agent/main.py`, `windmill/f/integrations/usage_report.py`, `tests/unit/test_usage_report.py`, `.gitignore`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_usage_report.py -q` — turnos `is_test` fora dos KPIs; Δ contra semana anterior e linha de base

- [ ] 2.4 Sonda diária somente-leitura + aviso único por integração/dia + `/jobs/probe` + script Windmill
  - SCN-USE-06
  - Files: `agent/services/probe.py`, `agent/main.py`, `windmill/f/integrations/probe.py`, `tests/unit/test_probe.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_probe.py -q` — nenhuma tool de escrita é importada pelo módulo; OAuth expirado gera 1 aviso mesmo com 2 execuções no dia

- [x] 2.5 Métricas `evi_turns_total{channel,outcome}` e `evi_probe_failures_total{check}`
  - SCN-USE-05
  - Files: `agent/services/metrics.py`, `tests/unit/test_metrics.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_metrics.py -q`

## 3. Ciclo com a simulação

- [x] 3.1 `evi-sim promote <turn_id>` com anonimização estável e `expect` TODO; runner recusa TODO
  - SCN-USE-07
  - Files: `agent/testing/sim/promote.py`, `agent/testing/sim/runner.py`, `scripts/evi-sim`, `tests/unit/test_sim_promote.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_promote.py -q` — nenhum telefone, e-mail ou nome do seed original no YAML gerado

- [ ] 3.2 Assinatura de formato de payload do Evolution + gravação estrutural de formatos novos
  - SCN-USE-08
  - Files: `agent/services/payload_shapes.py`, `agent/main.py`, `tests/unit/test_payload_shapes.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_payload_shapes.py -q` — payload gravado não contém nenhum valor de texto original

- [ ] 3.3 Regra "Validação em uso real" em `config.yaml`, `docs/testing.md` (L4), sincronizar spec e arquivar
  - Files: `openspec/config.yaml`, `docs/testing.md`, `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `openspec validate --specs && PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-sim run --tag critical --repeat 3 --llm live && ./scripts/evi-sim run --tag critical --llm replay` (regravar cassettes se o prompt mudou)
