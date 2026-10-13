## 1. Fonte

- [x] 1.1 (Verify `evi-test windmill` não existe; coberto pelo teste unitário) Script Windmill `list_contacts` (People API paginada → só nome + telefones) + fixture + passo OAuth `gcontacts` no `windmill/README.md`
  - SCN-NAME-01
  - Files: `windmill/f/integrations/list_contacts.py`, `windmill/f/integrations/list_contacts.script.yaml`, `tests/fixtures/google/people_connections.json`, `windmill/README.md`, `tests/unit/test_windmill_list_contacts.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_windmill_list_contacts.py -q` e `./scripts/evi-test windmill`

## 2. Aplicação

- [x] 2.1 `name_source` em `whatsapp_contacts` (migração: nomes atuais com alias de vCard → `vcard`; os gravados por `set_whatsapp_contact_name` → `user`)
  - SCN-NAME-02
  - Files: `agent/db.py`, `agent/services/contact_registry.py`, `agent/tools/contact_tool.py`, `tests/unit/test_db.py`, `tests/unit/test_contact_registry.py`
  - Verify: `DATABASE_URL=<PG efêmero> EVI_TEST_EPHEMERAL_DB=1 PYTHONPATH=agent python3 -m pytest tests/unit/test_db.py tests/unit/test_contact_registry.py -q`

- [x] 2.2 `apply_entries()` genérico (vCard vira produtor); ambíguos reportados; `user` nunca sobrescrito
  - SCN-NAME-02, SCN-NAME-03, SCN-MEM-12
  - Files: `agent/services/vcard_import.py`, `tests/unit/test_vcard_import.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_vcard_import.py -q` e `./scripts/evi-test vcard`

- [x] 2.3 `contact_names.sync()` + `POST /jobs/contact-names-sync` + `./scripts/evi-test contact-names-sync` (dry-run padrão)
  - SCN-NAME-01, SCN-NAME-03
  - Files: `agent/services/contact_names.py`, `agent/main.py`, `agent/testing/cli.py`, `tests/unit/test_contact_names.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_names.py -q` e `./scripts/evi-test smoke`

- [x] 2.4 Nome via `canonical_jid()`: `@lid` pareado herda nome; resumo do WhatsApp e dívidas usam
  - SCN-NAME-04
  - Files: `agent/services/contact_registry.py`, `agent/services/evolution_discovery.py`, `tests/unit/test_contact_registry.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_registry.py tests/unit/test_whatsapp_activity.py -q`

## 3. Pergunta semanal

- [x] 3.1 Seção "Conversas sem nome" no briefing de segunda (até 3) + respostas "nomeia N <nome>" / "ignora N"
  - SCN-NAME-05
  - Files: `agent/services/briefing.py`, `agent/services/contact_names.py`, `tests/unit/test_briefing.py`, `tests/unit/test_contact_names.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py tests/unit/test_contact_names.py -q` e `./scripts/evi-test briefing`

- [x] 3.2 Sugestão de nome `CONTACT_NAME_HINT` (evidência literal validada) + casos no avaliador
  - SCN-NAME-06
  - Files: `agent/services/contact_names.py`, `agent/testing/llm_eval/contact_name_hint.py`, `tests/eval/contact_name_hint_cases.yaml`, `tests/unit/test_contact_names.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_names.py -q` e `./scripts/evi-test llm-eval contact-name-hint --cases synthetic`

## 4. Fechamento

- [ ] 4.1 Cenários `SIM-NAME-*` (agenda nomeia número; nome do usuário não é sobrescrito; pergunta semanal → "nomeia 1 X" → resumo mostra X); `docs/testing.md`
  - SCN-NAME-03, SCN-NAME-05
  - Files: `tests/sim/scenarios/contact-names/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag contact-names --repeat 3 --llm live` (3/3) e `./scripts/evi-sim run --tag critical --repeat 3 --llm live`

- [ ] 4.2 Reconexão OAuth `gcontacts` (usuário), dry-run real revisado, primeira sincronização, agendamento 03:15; gates; BACKLOG + Progress
  - SCN-NAME-01
  - Files: `windmill/f/integrations/list_contacts.schedule.yaml`, `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
