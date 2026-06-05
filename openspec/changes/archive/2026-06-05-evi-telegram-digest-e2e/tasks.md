## 1. Reply loop

- [x] 1.1 SCN-TG-02: webhook sends `sendMessage` to update chat.id
  - Files: `agent/main.py`, `agent/services/telegram_notify.py`
  - Verify: `./scripts/evi-telegram-verify.sh`

- [x] 1.2 Windmill script stdlib
  - Files: `windmill/f/integrations/telegram_to_evi.py`
  - Verify: `wmill sync push` (manual)

## 2. E2E

- [x] 2.1 Verify script send + webhook + digest
  - Files: `scripts/evi-telegram-verify.sh`, `docs/testing.md`
  - Verify: `./scripts/evi-telegram-verify.sh`
