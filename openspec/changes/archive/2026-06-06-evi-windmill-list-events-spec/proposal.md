## Why

SCN-CAL-06 is in spec and covered by unit mocks only; no Tier 2 live harness verifies `list_calendar_events` against Windmill + gcal OAuth.

## What Changes

- `run_calendar_list()` in `agent/testing/cli.py`
- `./scripts/evi-test calendar-list [--live-windmill]`
- Update `docs/testing.md` and testing spec with live scenario

**Out of scope:** Changing `windmill/f/integrations/list_events.py`; new containers.

## Capabilities

### Modified Capabilities

- `integrations-windmill`: SCN-CAL-06 live trace
- `testing`: calendar-list harness mapping

## Impact

Test harness and docs only.
