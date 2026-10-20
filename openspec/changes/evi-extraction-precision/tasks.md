## 1. Dívidas de resposta

- [x] 1.1 Vocabulário de encerramento v3 e regra de aceno (≤ 3 palavras, sem pedido, ≤ 10 min após a última fala do usuário; precisa de `last_out_at`)
  - SCN-PREC-01, SCN-PREC-02
  - Files: `agent/services/reply_debts.py`, `agent/db.py`, `tests/unit/test_reply_debts.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reply_debts.py tests/unit/test_db.py -q`

- [x] 1.2 Coluna `last_out_preview` (gravada em `record_outbound`) e contexto no item do briefing ("você: …")
  - SCN-PREC-03
  - Files: `agent/db.py`, `agent/services/reply_debts.py`, `agent/services/briefing.py`, `tests/unit/test_briefing.py`, `tests/unit/test_db.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py tests/unit/test_db.py -q`

- [x] 1.3 Juiz de dívida: tarefa `DEBT` em `llm_structured`, `debt_judge.py` (contexto da timeline, `wrap_external`, veredito por `last_in_id`), colunas `judge_*`, `list_debts` lê veredito; `judge_candidates` no `reminder_loop` e antes do briefing; flag `EVI_DEBT_JUDGE`
  - SCN-PREC-04, SCN-PREC-05
  - Files: `agent/services/debt_judge.py`, `agent/services/llm_structured.py`, `agent/services/reply_debts.py`, `agent/services/reminder_loop.py`, `tests/unit/test_debt_judge.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_debt_judge.py tests/unit/test_reply_debts.py tests/unit/test_llm_structured.py -q`

- [x] 1.4 `llm-eval debt` (casos sintéticos incl. a conversa do Felipe e pedidos sem "?") com limiar de acurácia
  - SCN-PREC-04
  - Files: `agent/testing/llm_eval/debt.py`, `agent/testing/cli.py`, `tests/eval/debt_cases.yaml`, `tests/unit/test_llm_eval.py`
  - Verify: `./scripts/evi-test llm-eval debt`

## 2. Tarefas extraídas por regex

- [x] 2.1 Juiz de tarefa: `task` sem data de `extract_commitment` (com reply debts ligado) entra como `needs_eval`; `task_judge.py` (tarefa `TASK`, `keep=false` → `dismissed`/`auto-eval`), fallback de 48 h; flag `EVI_TASK_JUDGE`; eventos inalterados
  - SCN-PREC-06, SCN-PREC-07
  - Files: `agent/main.py`, `agent/services/task_judge.py`, `agent/services/reminder_loop.py`, `agent/db.py`, `tests/unit/test_task_judge.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_task_judge.py tests/unit/test_promises.py tests/unit/test_whatsapp_processor.py -q`

- [x] 2.2 `llm-eval task` (casos: "As empresas gostam do fornecedor enviar a NF" → descarta; "vou te mandar o relatório amanhã" → mantém)
  - SCN-PREC-06
  - Files: `agent/testing/llm_eval/task.py`, `agent/testing/cli.py`, `tests/eval/task_cases.yaml`, `tests/unit/test_llm_eval.py`
  - Verify: `./scripts/evi-test llm-eval task`

## 3. Reações do Telegram

- [x] 3.1 `message_reaction` em `ALLOWED_UPDATES` e no modelo do webhook; reação 👍/👎 em mensagem do briefing → `set_briefing_feedback` (última vence; só chat autorizado)
  - SCN-PREC-08
  - Files: `agent/services/telegram_poller.py`, `agent/services/telegram_handler.py`, `agent/main.py`, `tests/unit/test_telegram_handler.py`, `tests/unit/test_telegram_poller.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_handler.py tests/unit/test_telegram_poller.py -q`

- [x] 3.2 `turn_log.tg_message_id` gravado no envio da resposta do chat; reação 👍/👎 nessa mensagem → `feedback` `bom`/`ruim`; relatório semanal conta reações junto com botões e `/bom` `/ruim`
  - SCN-PREC-09
  - Files: `agent/db.py`, `agent/services/telegram_handler.py`, `agent/services/telegram_notify.py`, `agent/services/usage_report.py`, `tests/unit/test_telegram_handler.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_handler.py tests/unit/test_usage_report.py tests/unit/test_db.py -q`

## 4. Simulação, segurança e fechamento

- [ ] 4.1 Cenários `SIM-DEBT-10` (aceno "Boa" logo após fala do usuário não vira dívida), `SIM-DEBT-11` (mensagem ambígua julgada como pedido continua dívida, com contexto) e `SIM-PREC-01` (frase genérica com "enviar" não vira tarefa); cassetes; `docs/testing.md`
  - Estado 2026-10-20: cenários e cassetes novos gravados (live x3 verde); faltam regravar SIM-DEBT-06 e SIM-SCHED-02 (limite mensal do Gemini estourou)
  - SCN-PREC-01, SCN-PREC-05, SCN-PREC-06
  - Files: `tests/sim/scenarios/reply-debts/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --tag reply-debts --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [x] 4.2 Revisão leve de segurança (novas tarefas de LLM com conteúdo de terceiros): `docs/security/threat-model.md`, `./scripts/evi-security-scan`, `docs/security/findings.md`
  - Files: `docs/security/threat-model.md`, `docs/security/findings.md`
  - Verify: `./scripts/evi-security-scan --ci`

- [ ] 4.3 Deploy (recriar `agent-api`), gates e BACKLOG/Progress/roadmap
  - Files: `openspec/BACKLOG.md`, `Progress.md`, `openspec/specs/roadmap.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
