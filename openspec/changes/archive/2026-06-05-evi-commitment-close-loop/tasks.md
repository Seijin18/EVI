## 1. Confirm loop

- [x] 1.1 SCN-CHAT-04: `confirm_commitments` calls `create_task` for `type=task`, marks scheduled on `created`
  - Files: `agent/tools/commitment_tools.py`
  - Verify: `PYTHONPATH=agent python3 tests/unit/test_commitment_tools.py`

- [x] 1.2 Update graph hint for task confirm path
  - Files: `agent/graph.py`
  - Verify: `grep confirm_commitments agent/graph.py`

## 2. Tests

- [x] 2.1 Unit tests for list/confirm/dismiss (mock Windmill)
  - Files: `tests/unit/test_commitment_tools.py`
  - Verify: `pytest tests/unit/test_commitment_tools.py -q`

- [x] 2.2 Tier 2 `evi-test commitments` (Postgres seed + list tool)
  - Files: `agent/testing/cli.py`, `scripts/evi-test`
  - Verify: `DATABASE_URL=postgresql://evi:changeme@localhost:5432/evidb ./scripts/evi-test commitments`

- [x] 2.3 Fix live tasks assertion for SCN-TASK-05
  - Files: `agent/testing/cli.py`
  - Verify: `./scripts/evi-test tasks --live-windmill` (skip ok if Windmill down)

## 3. Docs

- [x] 3.1 Map SCN-CHAT-02/03/04 and SCN-WA-10 in testing guide
  - Files: `docs/testing.md`
  - Verify: `grep SCN-CHAT docs/testing.md`

## 4. Archive prep

- [x] 4.1 Full offline verify before archive
  - Files: —
  - Verify: `pytest tests/unit -q && ./scripts/evi-test smoke`
