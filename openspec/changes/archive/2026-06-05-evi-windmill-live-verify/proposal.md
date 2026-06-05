# Proposal: evi-windmill-live-verify

## Why

Calendar already has Tier 2 live verification (`SCN-CAL-04`); Gmail and Google Tasks scripts exist but `evi-test email` is fixture-only and `evi-test tasks` live assertions are loose. Productivity P1 requires closing the Google loop with documented OAuth and strict live harness before ops work.

## What Changes

- Add `SCN-EMAIL-05` live scenario for `./scripts/evi-test email --live-windmill`
- Extend `run_email(live_windmill)` and harden `run_tasks` live checks in `agent/testing/cli.py`
- Document `gmail` / `gcloud` Windmill resources and env vars in `windmill/README.md` and `.env.example`
- Tier 1 unit test for `summarize_inbox` wiring (mock `post_windmill`)
- Update `roadmap.md` when archived (Windmill live verify → Done)

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `integrations-windmill`: ADD `SCN-EMAIL-05` live email verify; clarify `SCN-TASK-05` assertion
- `tools-productivity`: ADD `SCN-EMAIL-05` trace for email live harness
- `testing`: ADD trace scenarios for `SCN-EMAIL-05` and `SCN-TASK-05` in docs/testing.md

## Impact

- `agent/testing/cli.py`, `tests/unit/`, `windmill/README.md`, `.env.example`, `docs/testing.md`
- No new containers; uses existing Windmill + OAuth resources

## Out of scope

Neo4j, MCP, RAG, compose healthchecks (separate change), Meta WhatsApp, new Windmill scripts.
