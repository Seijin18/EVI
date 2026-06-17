# Tasks

- [x] 1. Compose + env v3
  **Files:** `docker-compose.yml`, `.env.example`
  **Verify:** `docker compose config | grep EVI_WORKSPACE`

- [x] 2. Fix control channel unit tests
  **Files:** `tests/unit/test_whatsapp_control.py`, `tests/unit/test_telegram_handler.py`
  **Verify:** `PYTHONPATH=agent pytest tests/unit/test_whatsapp_control.py tests/unit/test_telegram_handler.py -q`

- [x] 3. Tier 2 runtime-v3 + inbox-ux
  **Files:** `agent/testing/cli.py`, `tests/fixtures/windmill/email_summary_messages.json`
  **Verify:** `./scripts/evi-test runtime-v3 && ./scripts/evi-test inbox-ux`

- [x] 4. Chat invoke integration test
  **Files:** `tests/unit/test_chat_invoke.py`
  **Verify:** `PYTHONPATH=agent pytest tests/unit/test_chat_invoke.py -q`

- [x] 5. Docs, CI, live script
  **Files:** `docs/testing.md`, `.github/workflows/ci.yml`, `scripts/evi-inbox-ux-verify.sh`
  **Verify:** `./scripts/evi-test smoke` (14/14)
