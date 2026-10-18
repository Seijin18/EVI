## 1. Envio

- [x] 1.1 `telegram_notify`: `reply_markup` em `send_telegram_message` (com fallback sem teclado), `answer_callback(query_id, text)`, `edit_reply_markup(chat_id, message_id, markup)`
  - SCN-UX-06
  - Files: `agent/services/telegram_notify.py`, `tests/unit/test_telegram_notify.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_notify.py -q`

- [x] 1.2 Briefing monta o teclado (itens acionáveis visíveis + 👍/👎) e envia com ele; `briefing_log.feedback`; flag `EVI_BRIEFING_BUTTONS`
  - SCN-UX-06
  - Files: `agent/services/briefing.py`, `agent/db.py`, `tests/unit/test_briefing.py`, `.env.example`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_briefing.py -q` e `./scripts/evi-test briefing`

## 2. Toque

- [x] 2.1 `getUpdates` com `allowed_updates`; `process_telegram_update` trata `callback_query`: allowlist, parse estrito, dia do snapshot, ação determinística, `answerCallbackQuery`, edição do teclado, `replied_at`, `turn_log`
  - SCN-UX-07, SCN-UX-08
  - Files: `agent/services/telegram_poller.py`, `agent/services/telegram_handler.py`, `agent/services/briefing.py`, `tests/unit/test_telegram_handler.py`, `tests/unit/test_telegram_poller.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_handler.py tests/unit/test_telegram_poller.py -q`

## 3. Simulação e fechamento

- [x] 3.1 Fake do Telegram com `callback_query`, `answerCallbackQuery`, `editMessageReplyMarkup` e `reply_markup` registrado; cenário `SIM-UX-04` (toque ✅ numa dívida → reconhecida; 👍 gravado; botão de ontem recusado); cassetes; `docs/testing.md`
  - SCN-UX-06, SCN-UX-07, SCN-UX-08
  - Files: `agent/testing/sim/fake_telegram.py`, `agent/testing/sim/runner.py`, `tests/sim/scenarios/briefing/`, `tests/sim/cassettes/`, `docs/testing.md`
  - Verify: `./scripts/evi-sim run --id SIM-UX-04 --repeat 3 --llm live` e `./scripts/evi-sim run --tag critical --llm replay`

- [ ] 3.2 Deploy, gates, BACKLOG + Progress
  - SCN-UX-06
  - Files: `openspec/BACKLOG.md`, `Progress.md`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q`, `./scripts/evi-test smoke`, `openspec validate --specs`, `ruff check agent/ --select E,W,F --ignore E501`
