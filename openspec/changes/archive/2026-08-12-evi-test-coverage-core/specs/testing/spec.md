## ADDED Requirements

### Requirement: The critical path carries unit coverage
Every module on the traffic-carrying path SHALL have a unit test file: the Telegram poller (the production `TELEGRAM_MODE=polling` entry point), the Evolution client (outbound WhatsApp), `db.py` (durable state), and `main.py`'s Evolution webhook.

The poller tests SHALL cover the three loop invariants whose failure stops the bot silently: it survives a handler exception, it survives a transport failure, and the offset advances past processed updates instead of replaying them.

`db.py` SHALL be tested against a real Postgres rather than a mocked driver — its contract is SQL (`ON CONFLICT … DO NOTHING`, `WHERE status = 'pending'`), which a mock cannot verify. The tests SHALL skip when `DATABASE_URL` is unset, and CI SHALL provide an ephemeral Postgres service so they run there.

#### Scenario: SCN-DB-01
- **WHEN** `tests/unit/test_db.py` runs with `DATABASE_URL` pointing at a fresh database
- **THEN** migrations are idempotent, a duplicate `(source, source_id)` is rejected, a second confirm cannot rewrite an audited row, and the removed `dev_jobs` / `dev_bridge_state` tables are not recreated

#### Scenario: SCN-TG-06
- **WHEN** `tests/unit/test_telegram_poller.py` runs
- **THEN** a handler exception and a transport failure both leave the loop running, and the offset becomes the highest `update_id` + 1

#### Scenario: SCN-API-03
- **WHEN** `tests/unit/test_main_endpoints.py` runs
- **THEN** the Evolution webhook ingests a normal message, skips its own `[EVI]` echo, routes a control JID to chat, refuses a replayed message id, filters groups and own messages, and records a reason in the JSONL trace for every drop
