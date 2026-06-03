# Proposal: evi-test-harness

## Intent
Add consistent Tier 1–3 testing so each EVI feature can be validated in isolation, including WhatsApp commitment extraction via terminal fixtures and JSONL logs.

## Scope
- `tests/`, `scripts/evi-test`, `agent/testing/cli.py`, `agent/services/whatsapp_processor.py`
- `docs/testing.md`, `openspec/specs/testing/spec.md`

## Out of scope
- CI GitHub Actions
- Live WhatsApp API
