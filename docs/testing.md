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
| Calendar (live Windmill) | `./scripts/evi-test calendar --live-windmill` |
| Evolution parse | `./scripts/evi-test evolution` |
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

## E2E checklist (SCN-E2E)

| Step | Command | Pass criteria |
|------|---------|---------------|
| SCN-E2E-01 | `docker compose up -d --build` | qdrant, postgres, agent-api, windmill healthy |
| SCN-E2E-02 | `./scripts/evi-test smoke` | 12/12 offline |
| SCN-E2E-03 | `export DATABASE_URL=postgresql://evi:PASS@localhost:5432/evidb` | session test connects |
| SCN-E2E-04 | Ollama running on host | `curl host.docker.internal:11434` from agent |
| SCN-E2E-05 | `./scripts/evi-test smoke --full` | chat PASS or documented skip |
| SCN-E2E-06 | `./scripts/evi-test evolution` | parse fixture PASS |

Record run date and results in this section when validating locally.

### Last run

- Offline smoke: run `./scripts/evi-test smoke` after changes
- Full stack: requires Ollama + compose (see SCN-E2E-04/05)
