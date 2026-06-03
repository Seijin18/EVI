# EVI testing guide

Three tiers:

1. **Unit** — `pytest tests/unit -q` (no Docker/Ollama)
2. **Integration CLI** — `./scripts/evi-test <feature> [--verbose]`
3. **Smoke E2E** — `./scripts/evi-test smoke --full` (needs agent-api + Ollama)

## Commands

| Feature | Command |
|---------|---------|
| All offline smoke | `./scripts/evi-test smoke` |
| Full stack | `./scripts/evi-test smoke --full` |
| WhatsApp pipeline | `./scripts/evi-test whatsapp --verbose` |
| File organizer | `./scripts/evi-test file-organizer` |
| Calendar (mock) | `./scripts/evi-test calendar` |
| Calendar (live n8n) | `./scripts/evi-test calendar --live-n8n` |
| Notes | `./scripts/evi-test notes` |
| Session/Postgres | `DATABASE_URL=... ./scripts/evi-test session` |

## WhatsApp logs

```bash
./scripts/evi-test whatsapp --verbose
jq -s '.' logs/whatsapp_*.jsonl | less
```

Golden file: `tests/golden/whatsapp_commitments.json`

## OpenSpec verify

```bash
pytest tests/unit -q && ./scripts/evi-test smoke
```

Scenario IDs (`SCN-*`) are defined in `openspec/specs/testing/spec.md`.
