## Why

The P0–P3 OpenSpec roadmap is implemented and archived, but the WhatsApp commitment loop is incomplete: `confirm_commitments` marks task-type rows as scheduled without calling Windmill `create_task`, and several SCN scenarios lack Tier 1/2 verification (SCN-CHAT-02/03, SCN-WA-10, live Tasks/Gmail).

## What Changes

- Wire `confirm_commitments` to `create_task` for `type=task` commitments (events still use `schedule_event`).
- Add `evi-test commitments` covering Postgres queue, list tool, and optional live confirm.
- Add unit tests for `commitment_tools` confirm/dismiss paths.
- Fix `evi-test tasks --live-windmill` to assert `"status":"created"` (matches Windmill script).
- Update `docs/testing.md` scenario map and E2E checklist (13/13 smoke, commitment flows).

**Out of scope:** Telegram digest E2E (SCN-WA-12), compose healthchecks, Neo4j, Meta WhatsApp adapter, new containers.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `agent-api`: extend SCN-CHAT-03 — confirm tasks via Windmill, not only calendar events.
- `messaging-whatsapp`: document SCN-WA-10 verification via `evi-test commitments`.
- `testing`: add SCN-CHAT-02/03 and commitment Tier 2 command mapping.
- `integrations-windmill`: align live task test with SCN-TASK-05 `created` response.

## Impact

- `agent/tools/commitment_tools.py`, `agent/testing/cli.py`, `scripts/evi-test`
- `tests/unit/test_commitment_tools.py`, `docs/testing.md`
- Delta specs under this change folder
