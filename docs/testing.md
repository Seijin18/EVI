# EVI testing guide

Three tiers:

1. **Unit** — `pytest tests/unit -q` (no Docker/Ollama)
2. **Integration CLI** — `./scripts/evi-test <feature> [--verbose]`
3. **Smoke E2E** — `./scripts/evi-test smoke --full` (needs agent-api + Ollama)

## Commands

| Feature | Command | SCN |
|---------|---------|-----|
| All offline smoke | `./scripts/evi-test smoke` | SCN-E2E-02 |
| Full stack | `./scripts/evi-test smoke --full` | SCN-E2E-05 |
| WhatsApp pipeline | `./scripts/evi-test whatsapp --verbose` | SCN-WA-04 |
| Commitments queue | `DATABASE_URL=... ./scripts/evi-test commitments` | SCN-WA-10, SCN-CHAT-02 |
| File organizer | `./scripts/evi-test file-organizer` | SCN-FO-01 |
| Calendar (mock) | `./scripts/evi-test calendar` | SCN-CAL-02 |
| Calendar (live Windmill) | `./scripts/evi-test calendar --live-windmill` | SCN-CAL-04 |
| Tasks (mock) | `./scripts/evi-test tasks` | SCN-TASK-03 |
| Tasks (live Windmill) | `./scripts/evi-test tasks --live-windmill` | SCN-TASK-05 |
| Email (mock) | `./scripts/evi-test email` | SCN-EMAIL-04 |
| Email (live Windmill) | `./scripts/evi-test email --live-windmill` | SCN-EMAIL-05 |
| Evolution parse | `./scripts/evi-test evolution` | SCN-WA-05 |
| Telegram (live E2E) | `./scripts/evi-telegram-verify.sh` | SCN-TG-02, SCN-WA-12 |
| Telegram (mock) | `./scripts/evi-test telegram` | SCN-TG-01 |
| Telegram (live webhook) | `./scripts/evi-test telegram --live-telegram` | SCN-TG-02 |
| Notes | `./scripts/evi-test notes` | SCN-NOTE-02 |
| Session/Postgres | `DATABASE_URL=... ./scripts/evi-test session` | SCN-E2E-03 |

### Unit tests (commitment review)

| SCN | Test file |
|-----|-----------|
| SCN-CHAT-03 | `tests/unit/test_commitment_tools.py` — confirm event → `schedule_event` |
| SCN-CHAT-04 | `tests/unit/test_commitment_tools.py` — confirm task → `create_task` |
| SCN-EMAIL-03 | `tests/unit/test_email_tool.py` — `summarize_inbox` wiring |
| SCN-WA-09 | `tests/unit/test_evolution_filter.py` |
| SCN inbox priority | `tests/unit/test_commitment_priority.py` |

```bash
pytest tests/unit/test_commitment_tools.py -q
```

## WhatsApp logs

```bash
./scripts/evi-test whatsapp --verbose
jq -s '.' logs/whatsapp_*.jsonl | less
```

Golden file: `tests/golden/whatsapp_commitments.json`

## OpenSpec verify

```bash
pytest tests/unit -q && ./scripts/evi-test smoke
openspec validate --specs
```

Scenario IDs are defined in `openspec/specs/*/spec.md`.

## E2E checklist (SCN-E2E)

| Step | Command | Pass criteria |
|------|---------|---------------|
| SCN-E2E-01 | `docker compose up -d --build` | postgres → qdrant/windmill healthy → agent-api (SCN-OPS-01) |
| SCN-OPS-01 | `docker compose ps` | postgres, qdrant, windmill-server, agent-api show `healthy` |
| SCN-E2E-02 | `./scripts/evi-test smoke` | 13/13 offline |
| SCN-E2E-03 | `export DATABASE_URL=postgresql://evi:PASS@localhost:5432/evidb` | session + commitments connect |
| SCN-E2E-04 | Ollama running on host (not in compose) | `curl host.docker.internal:11434` from agent; chat retries until model loads |
| SCN-E2E-05 | `./scripts/evi-test smoke --full` | chat PASS or documented skip |
| SCN-E2E-06 | `./scripts/evi-test evolution` | parse fixture PASS |
| SCN-CHAT-02 | `DATABASE_URL=... ./scripts/evi-test commitments` | list tool returns seeded row |

### Last run

- **2026-06-05** — `evi-commitment-close-loop`: run `pytest tests/unit -q && ./scripts/evi-test smoke` after apply
- Full stack: requires Ollama + compose (see SCN-E2E-04/05)
