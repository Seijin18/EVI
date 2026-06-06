## 1. Harness

- [x] 1.1 Add `run_calendar_list` to cli.py
  - Files: `agent/testing/cli.py`
  - Verify: `./scripts/evi-test calendar-list`

## 2. Docs and spec

- [x] 2.1 Map SCN-CAL-06 live in docs and testing spec
  - Files: `docs/testing.md`, `openspec/specs/testing/spec.md`
  - Verify: `grep calendar-list docs/testing.md`

## 3. Validate

- [x] 3.1 Unit + offline harness
  - Files: —
  - Verify: `python3 tests/unit/test_telegram_list.py && openspec validate evi-windmill-list-events-spec`
