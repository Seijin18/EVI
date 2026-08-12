## 1. Implementation

- [x] 1.1 Telegram poller — loop survival and offset advance
  - SCN-TG-06
  - Files: `tests/unit/test_telegram_poller.py`
  - Verify: `pytest tests/unit/test_telegram_poller.py -q`

- [x] 1.2 Evolution client — send path, echo guard, query limits
  - SCN-WA-18
  - Files: `tests/unit/test_evolution_client.py`
  - Verify: `pytest tests/unit/test_evolution_client.py -q`

- [x] 1.3 `db.py` against a real Postgres, skipped without `DATABASE_URL`
  - SCN-DB-01
  - Files: `tests/unit/test_db.py`
  - Verify: `DATABASE_URL=... pytest tests/unit/test_db.py -q`

- [x] 1.4 `main.py` endpoints and the Evolution webhook
  - SCN-API-03
  - Files: `tests/unit/test_main_endpoints.py`
  - Verify: `pytest tests/unit/test_main_endpoints.py -q`

- [x] 1.5 Ephemeral Postgres service in CI
  - SCN-DB-01
  - Files: `.github/workflows/ci.yml`
  - Verify: the unit-test step runs with `DATABASE_URL` set; `test_db.py` no longer skips

- [x] 1.6 Spec delta
  - Files: `openspec/changes/evi-test-coverage-core/specs/testing/spec.md`
  - Verify: `openspec validate evi-test-coverage-core`

## 2. Close-out

- [x] 2.1 Full gate green
  - Verify: `pytest tests/unit -q && ./scripts/evi-test smoke && ruff check agent/ --select E,W,F --ignore E501 && ./scripts/evi-container-smoke.sh && openspec validate --specs`

- [x] 2.2 Update `Progress.md` + `openspec/BACKLOG.md`, then archive
