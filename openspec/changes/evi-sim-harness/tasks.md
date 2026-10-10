## 1. Costuras e isolamento

- [x] 1.1 `TELEGRAM_API_BASE` (default `https://api.telegram.org`) no envio e no poller
  - SCN-SIM-02
  - Files: `agent/services/telegram_notify.py`, `agent/services/telegram_poller.py`, `tests/unit/test_telegram_poller.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_poller.py tests/unit/test_send_result.py -q` — sem a env, URL idêntica à atual

- [x] 1.2 `docker-compose.sim.yml` + `Dockerfile.sim` (libfaketime) + `tests/sim/sim.env` + guarda de isolamento sobre o config renderizado
  - SCN-SIM-01
  - Files: `docker-compose.sim.yml`, `agent/Dockerfile.sim`, `tests/sim/sim.env`, `scripts/evi-sim`, `agent/testing/sim/guard.py`
  - Verify: `./scripts/evi-sim guard` passa; com `./data` montado ou token real injetado no env, aborta com o motivo; `./scripts/evi-sim up && ./scripts/evi-sim down` não toca volumes do projeto `evi`

## 2. Fakes

- [x] 2.1 Fake Google com estado (Calendar, Tasks, Gmail — subconjunto usado pelos scripts) + `/_sim/seed|state|reset`
  - SCN-SIM-03
  - Files: `agent/testing/sim/fake_google.py`, `tests/unit/test_sim_fake_google.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_fake_google.py -q` — endpoint não implementado responde 500 com a URL

- [x] 2.2 Fake Windmill executando os scripts reais de `windmill/f/integrations/` com `urlopen` roteado e falhas injetáveis
  - SCN-SIM-03, SCN-SIM-06
  - Files: `agent/testing/sim/fake_windmill.py`, `tests/unit/test_sim_fake_windmill.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_fake_windmill.py -q` — os 8 scripts rodam contra o fake Google; `oauth_expired` produz o mesmo envelope que `parse_windmill_result` classifica como `reason=oauth`

- [x] 2.3 Fake Telegram (`getMe`, `deleteWebhook`, `getUpdates` long-poll, `sendMessage` com falha transitória) + fake Evolution (`sendText` capturado, contatos do seed) + app dos fakes
  - SCN-SIM-02, SCN-SIM-05
  - Files: `agent/testing/sim/fake_telegram.py`, `agent/testing/sim/fake_evolution.py`, `agent/testing/sim/fakes.py`, `tests/unit/test_sim_fake_messaging.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_fake_messaging.py -q`

## 3. Runner e corpus

- [x] 3.1 Schema YAML de cenário + runner (relógio, passos, asserções de estado/efeitos/latência, reset entre cenários)
  - SCN-SIM-04
  - Files: `agent/testing/sim/schema.py`, `agent/testing/sim/runner.py`, `tests/unit/test_sim_schema.py`, `scripts/evi-sim`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_schema.py -q` e `./scripts/evi-sim run --id SIM-SMOKE-01` (cenário trivial "Oi" → resposta capturada no fake Telegram)

- [x] 3.2 Repetição, taxa de aprovação por tag, orçamento de chamadas ao LLM, relatório JSONL + Markdown
  - SCN-SIM-07
  - Files: `agent/testing/sim/runner.py`, `agent/testing/sim/report.py`, `tests/unit/test_sim_report.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_sim_report.py -q` — `critical` 2/3 reprova; `--max-llm-calls` interrompe com relatório parcial

- [x] 3.3 Corpus de uso real (11 cenários) + fluxo WhatsApp (3), com dados fictícios
  - SCN-SIM-04, SCN-SIM-05
  - Files: `tests/sim/scenarios/real-usage/`, `tests/sim/scenarios/whatsapp/`
  - Verify: `./scripts/evi-sim run --tag real-usage,whatsapp --repeat 3 --llm live` — registrar a taxa no relatório; cenário reprovado vira bug aberto ou ajuste de expectativa justificado no próprio YAML
  - As-built 2026-10-10: 15/15 no limiar (SIM-RU-08 3/3 após ajuste da docstring de `set_whatsapp_contact_name`); relatórios em `logs/sim/`

- [ ] 3.4 Cenários de falha (3) e adversariais (3)
  - SCN-SIM-06, SCN-SIM-08
  - Files: `tests/sim/scenarios/failure/`, `tests/sim/scenarios/adversarial/`
  - Verify: `./scripts/evi-sim run --tag failure,adversarial --repeat 3 --llm live` — adversariais 3/3 sem tool de escrita e sem mensagem a terceiros

## 4. CI e documentação

- [ ] 4.1 Provider `sim-replay` (só com `EVI_SIM=1`) + `--llm record|replay` + cassettes dos `critical` + job `sim-replay` na CI
  - SCN-SIM-09
  - Files: `agent/llm.py`, `agent/testing/sim/cassette.py`, `tests/sim/cassettes/`, `.github/workflows/ci.yml`, `tests/unit/test_sim_cassette.py`
  - Verify: `./scripts/evi-sim run --tag critical --llm replay` verde sem `EVI_SIM_GEMINI_API_KEY`; alterar um prompt faz falhar com "cassette stale"

- [ ] 4.2 `docs/testing.md` (níveis L0–L4, quando rodar cada um), aviso de dados reais em `evi-telegram-verify.sh`/`evi-inbox-ux-verify.sh`, sincronizar spec `testing` e arquivar
  - Files: `docs/testing.md`, `scripts/evi-telegram-verify.sh`, `scripts/evi-inbox-ux-verify.sh`, `CLAUDE.md`, `openspec/BACKLOG.md`
  - Verify: `openspec validate --specs && PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-test smoke && ./scripts/evi-sim run --tag critical --repeat 3 --llm live`
