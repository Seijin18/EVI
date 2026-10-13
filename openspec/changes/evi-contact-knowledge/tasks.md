## 1. Fontes

- [x] 1.1 `fromMe` diretas gravadas na timeline em `track_conversation` (sem entrar na extração)
  - SCN-MEM-14
  - Files: `agent/services/reply_debts.py`, `agent/services/message_timeline.py`, `tests/unit/test_reply_debts.py`, `tests/unit/test_message_timeline.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reply_debts.py tests/unit/test_message_timeline.py -q` e `./scripts/evi-test contact-memory`

- [x] 1.2 `ensure_contact` recusa grupos, canais e broadcasts
  - SCN-MEM-15
  - Files: `agent/services/contact_filesystem.py`, `tests/unit/test_contact_filesystem.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_filesystem.py -q`

- [x] 1.3 Identidade canônica `@lid` ↔ telefone: tabela `wa_jid_alias` (webhook + descoberta via `remoteJidAlt`), `canonical_jid()`; timeline, dívidas de resposta e resumo do WhatsApp usam o canônico; migração das pastas `@lid` (dry-run/`--apply`)
  - SCN-MEM-21
  - Files: `agent/services/contact_identity.py`, `agent/db.py`, `agent/services/message_timeline.py`, `agent/services/evolution_discovery.py`, `tests/unit/test_contact_identity.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_identity.py tests/unit/test_reply_debts.py -q` e `./scripts/evi-test contact-memory`

## 2. Conhecimento estruturado

- [x] 2.0 Avaliador `./scripts/evi-test llm-eval contact-knowledge` (portar os 8 casos simulados para `tests/eval/contact_knowledge_cases.yaml`; reais só em `data/eval/`)
  - SCN-LLM-EVAL-01
  - Files: `agent/testing/llm_eval/contact_knowledge.py`, `tests/eval/contact_knowledge_cases.yaml`, `tests/unit/test_llm_eval.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_llm_eval.py -q` e `./scripts/evi-test llm-eval contact-knowledge --cases synthetic`

- [x] 2.1 `contact_knowledge.py`: parse/escrita de `## Fatos`, `## Em aberto`, `## Notas`, `knowledge_updated`; `read_contact_knowledge`
  - SCN-MEM-16
  - Files: `agent/services/contact_knowledge.py`, `tests/unit/test_contact_knowledge.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_knowledge.py -q` — `## Notas` preservada byte a byte

- [x] 2.2 `update_contact_knowledge(jid)`: mensagens novas → `run_structured("CONTACT_KNOWLEDGE", …)` com fatos/itens numerados → validação (evidência na janela, `remove` por id, JSON inválido não escreve); `learn_contact` passa a usá-la, por jid; avaliador ≥ limiar do design
  - SCN-MEM-06, SCN-MEM-17, SCN-MEM-18
  - Files: `agent/services/contact_knowledge.py`, `agent/services/contact_learning.py`, `tests/unit/test_contact_knowledge.py`, `tests/unit/test_contact_learning.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_knowledge.py tests/unit/test_contact_learning.py -q` e `./scripts/evi-test contact-learning`

- [x] 2.3 Consumidores usam `read_contact_knowledge`: `get_contact_info`, `whatsapp_llm_extract._contact_context`, `promise_context.conversation_context(knowledge=…)`
  - SCN-MEM-16, SCN-DEBT-10
  - Files: `agent/tools/contact_tool.py`, `agent/services/whatsapp_llm_extract.py`, `agent/services/promise_context.py`, `tests/unit/test_contact_tool.py`, `tests/unit/test_promise_context.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_tool.py tests/unit/test_promise_context.py tests/unit/test_whatsapp_llm_extract.py -q`

## 3. Lote, agendamento e migração

- [x] 3.1 `run_contact_learn_batch`: só pastas com mensagens novas, por recência, `limit=15`, por jid
  - SCN-MEM-19
  - Files: `agent/services/contact_learn_cron.py`, `tests/unit/test_contact_learn_cron.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_learn_cron.py -q`

- [ ] 3.2 Agendamento diário 03:30 de `f/integrations/contact_learn` (yaml no repo se o sync suportar; senão passo na UI documentado e confirmado com o usuário)
  - SCN-MEM-19
  - Files: `windmill/f/integrations/`, `docs/windmill.md`
  - Verify: `./scripts/evi-test windmill` e schedule `enabled` listado no Windmill

- [ ] 3.3 Migração `contact-knowledge-migrate` (dry-run / `--apply`): `## Síntese (…)` → `history.md`
  - SCN-MEM-20
  - Files: `agent/services/contact_knowledge.py`, `agent/testing/cli.py`, `tests/unit/test_contact_knowledge.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_contact_knowledge.py -q` e `./scripts/evi-test contact-knowledge-migrate` (dry-run)

## 4. Simulação e fechamento

- [ ] 4.1 Cenários `SIM-MEM-*`: conversa com pedido → "Em aberto" com o item; metadado não vira fato; JSON inválido não apaga perfil; `get_contact_info` mostra fatos; regravar cassettes; `docs/testing.md`
  - SCN-MEM-16..18
  - Files: `tests/sim/scenarios/contact-memory/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag contact-memory --repeat 3 --llm live` (3/3) e `./scripts/evi-sim run --tag critical --repeat 3 --llm live`

- [ ] 4.2 Rodar migração (`--apply`) com o usuário, primeira execução do lote, auditoria de 5 perfis; gates finais; BACKLOG + Progress
  - SCN-MEM-20
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
