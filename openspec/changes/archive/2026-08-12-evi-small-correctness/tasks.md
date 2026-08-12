## 1. Implementation

- [x] 1.1 `SendResult` + shared retry helper
  - SCN-SEND-01
  - Files: `agent/services/send_result.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_send_result.py -q`

- [x] 1.2 Telegram sender retries transport errors and reports the reason
  - SCN-SEND-01, SCN-SEND-02
  - Files: `agent/services/telegram_notify.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_notify_retry.py -q`

- [x] 1.3 WhatsApp sender gets the same treatment
  - SCN-SEND-01, SCN-SEND-02
  - Files: `agent/messaging/evolution.py`, `agent/services/evolution_client.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_whatsapp_control.py -q`

- [x] 1.4 Surface `send_error` in handler responses without changing the booleans
  - SCN-SEND-02
  - Files: `agent/services/telegram_handler.py`, `agent/services/whatsapp_control.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_telegram_handler.py tests/unit/test_whatsapp_control.py -q`

- [x] 1.5 Harness prints the send failure reason
  - SCN-SEND-02
  - Files: `agent/testing/cli.py`
  - Verify: `./scripts/evi-test telegram` then `./scripts/evi-telegram-verify.sh` (live)

- [x] 1.6 Heartbeat compares dates, not markdown slices
  - SCN-MEM-11
  - Files: `agent/services/heartbeat.py`, `agent/services/contact_filesystem.py`, `agent/services/contact_memory_audit.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_heartbeat.py -q`

- [x] 1.7 Seen-id trim keeps the newest ids
  - SCN-WA-17
  - Files: `agent/services/evolution_filter.py`
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit/test_evolution_filter.py -q`

- [x] 1.8 Spec deltas
  - Files: `openspec/changes/evi-small-correctness/specs/{remote-access,messaging-whatsapp,data-long-memory}/spec.md`
  - Verify: `openspec validate evi-small-correctness`

## 2. Close-out

- [x] 2.1 Full gate green
  - Verify: `PYTHONPATH=agent python3 -m pytest tests/unit -q && ./scripts/evi-test smoke && ./scripts/evi-test sessions && ./scripts/evi-test runtime-v3 && ./scripts/evi-test inbox-ux && ruff check agent/ --select E,W,F --ignore E501 && openspec validate --specs`

- [x] 2.2 Live verify against the running stack, then archive
  - Verify: rebuilt `agent-api`, `/health` ok, and all three `SendResult` paths
    exercised in the running container without sending anything —
    `not_configured` (with detail), `empty_text`, and `transport` with 2 real
    retry attempts plus exactly one `soft-fail` line.
  - Left to the user (sends real messages): `./scripts/evi-telegram-verify.sh`
    should reach 3/3, and a failure now prints `send_error=<reason>` instead of a
    bare `telegram_sent=False`.
