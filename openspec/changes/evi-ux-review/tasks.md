## 1. Revisão

- [x] 1.1 (documento escrito; revisão do usuário assíncrona — pendência) `docs/ux/review-2026-10.md`: amostras reais por superfície (briefing manhã/noite, listas, respostas de comando, lembretes, erros, `/ajuda`) + checklist + achados priorizados; revisão com o usuário
  - SCN-UX-01
  - Files: `docs/ux/review-2026-10.md`
  - Verify: documento aprovado pelo usuário no chat

## 2. Briefing

- [x] 2.1 Duas renderizações (`text_user` limpo/escapado, `text_model` marcado); envio usa `text_user`, sessão grava `text_model`; guarda no `telegram_notify` contra marcador residual
  - SCN-UX-02, SCN-BRIEF-01
  - Files: `agent/services/briefing.py`, `agent/services/telegram_notify.py`, `agent/services/untrusted.py`, `tests/unit/test_briefing.py`, `tests/unit/test_telegram_notify.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py tests/unit/test_telegram_notify.py -q` e `./scripts/evi-test briefing`

- [x] 2.2 Formato HTML do Telegram (quem em negrito, uma linha por item, idade/prazo curtos, `+N` com comando, rodapé de comandos), fallback para texto puro se o Telegram recusar o HTML
  - SCN-UX-03
  - Files: `agent/services/briefing.py`, `agent/services/telegram_notify.py`, `tests/unit/test_briefing.py`, `tests/fixtures/briefing/`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py -q` e `./scripts/evi-test briefing`

- [x] 2.3 Regra de volume (≤ ~25 linhas; seções excedentes viram linha-resumo com comando)
  - SCN-UX-04
  - Files: `agent/services/briefing.py`, `tests/unit/test_briefing.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py -q`

- [x] 2.4 Fechamentos v2 ("joia", "tranquilo", agradecimento + vocativo) com os casos reais de 12/10
  - SCN-DEBT-03, SCN-UX-05
  - Files: `agent/services/reply_debts.py`, `tests/unit/test_reply_debts.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_reply_debts.py -q`

## 3. Outras superfícies

- [x] 3.1 Listas e respostas diretas (`telegram_list`, comandos) com a mesma regra de duas renderizações e o mesmo formato de item
  - SCN-UX-02
  - Files: `agent/services/telegram_list.py`, `agent/services/telegram_handler.py`, `tests/unit/test_telegram_list.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_list.py tests/unit/test_telegram_handler.py -q`

- [x] 3.2 Correções priorizadas na revisão (até 3, um commit cada; o resto → BACKLOG)
  - SCN-UX-01
  - Files: `docs/ux/review-2026-10.md`, `openspec/BACKLOG.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`

## 4. Fechamento

- [ ] 4.1 Cenários `SIM-UX-*` (briefing sem marcador e com HTML válido; "feito N" continua funcionando sobre o briefing novo); gates; BACKLOG + Progress
  - SCN-UX-02, SCN-UX-03
  - Files: `tests/sim/scenarios/briefing/`, `tests/sim/cassettes/`, `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `./scripts/evi-sim run --tag briefing --repeat 3 --llm live` (3/3), `./scripts/evi-sim run --tag critical --repeat 3 --llm live`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
