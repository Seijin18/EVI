## 1. Política e portões

- [ ] 1.1 Tabela `contact_policy` + `contact_policy.py` (`ingest_allowed`, `send_allowed`, `set_policy`, `list_restricted`, padrão por tipo, JID canônico, cache 60 s) + semente da `EVI_WHATSAPP_GROUP_WHITELIST`
  - SCN-POL-01, SCN-POL-02
  - Files: `agent/db.py`, `agent/services/contact_policy.py`, `tests/unit/test_contact_policy.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_policy.py tests/unit/test_db.py -q`

- [ ] 1.2 Portão de ingestão no webhook antes de estado/promessas/timeline; trace `reason: policy` sem texto; filtro de grupos e discovery passam a usar a política
  - SCN-POL-01, SCN-POL-02
  - Files: `agent/main.py`, `agent/services/evolution_filter.py`, `agent/services/evolution_discovery.py`, `tests/unit/test_evolution_filter.py`, `tests/unit/test_main_endpoints.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_evolution_filter.py tests/unit/test_main_endpoints.py -q` e `./scripts/evi-test evolution`

- [ ] 1.3 Guarda de envio em `send_whatsapp_text` (controle sempre permitido; `send` off ou grupo não liberado → falha com `policy_send_blocked`)
  - SCN-POL-03
  - Files: `agent/services/evolution_client.py`, `tests/unit/test_evolution_client.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_evolution_client.py -q`

## 2. Comandos

- [ ] 2.1 Resolução de alvo em código (nome, número, grupo; 0/1/N resultados) e confirmação com nome + número e botões `p1:` ✅/✖
  - SCN-POL-04
  - Files: `agent/services/contact_policy.py`, `agent/services/telegram_handler.py`, `tests/unit/test_contact_policy.py`, `tests/unit/test_telegram_handler.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_policy.py tests/unit/test_telegram_handler.py -q`

- [ ] 2.2 Comandos `para de ler`/`volta a ler`, `não envia para`/`pode enviar para`, `libera`/`bloqueia o grupo`, `/privacidade`; `/ajuda` atualizado
  - SCN-POL-04, SCN-POL-05
  - Files: `agent/services/chat_commands.py`, `agent/services/telegram_handler.py`, `tests/unit/test_chat_commands.py`, `tests/unit/test_telegram_handler.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_chat_commands.py tests/unit/test_telegram_handler.py -q`

- [ ] 2.3 Apagar dados do contato bloqueado (`purge`: diretório do contato, `wa_conversation_state`, `pending_commitments`, `awaiting_dismissed`, vereditos; aliases incluídos) só com ✅
  - SCN-POL-06
  - Files: `agent/services/contact_policy.py`, `agent/services/contact_filesystem.py`, `agent/db.py`, `tests/unit/test_contact_policy.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_policy.py -q`

## 3. Operação, segurança e simulação

- [ ] 3.1 `setup-evolution.sh` com `groupsIgnore=false` sempre; `.env.example` (whitelist = semente) e `docs/evolution.md`
  - SCN-POL-02
  - Files: `scripts/setup-evolution.sh`, `.env.example`, `docs/evolution.md`
  - Verify: `bash -n scripts/setup-evolution.sh` e `grep -n "groupsIgnore" scripts/setup-evolution.sh`

- [ ] 3.2 Revisão leve de segurança (nova superfície: comandos de política e exclusão de dados): threat model, scan, achados
  - SCN-POL-06
  - Files: `docs/security/threat-model.md`, `docs/security/findings.md`
  - Verify: `./scripts/evi-security-scan`

- [ ] 3.3 Cenários `SIM-POL-01` (contato bloqueado → nada gravado; volta a ler → grava) e `SIM-POL-02` (grupo descartado por padrão; liberado → ingerido)
  - SCN-POL-01, SCN-POL-02, SCN-POL-04
  - Files: `tests/sim/scenarios/policy/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag policy --repeat 3 --llm fill` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.4 Gates, BACKLOG + Progress
  - SCN-POL-01
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `./scripts/evi-sim run --tag critical --repeat 3 --llm fill`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
