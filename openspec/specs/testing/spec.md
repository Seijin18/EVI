# Testing requirements

## Purpose

Define how EVI features are verified with minimal context (evi-test + SCN IDs).

## Requirements

### Requirement: Tiered verification
Every feature domain MUST have Tier 1 (pytest) and Tier 2 (`./scripts/evi-test <feature>`) coverage before OpenSpec archive.

#### Scenario: Unit suite
- **WHEN** `pytest tests/unit -q` runs
- **THEN** all SCN-marked unit tests pass without network

#### Scenario: Offline smoke
- **WHEN** `./scripts/evi-test smoke` runs without Docker
- **THEN** memory, file-organizer, whatsapp, calendar (mock), notes, telegram parse pass

### Requirement: Scenario traceability
Domain specs MUST map scenario IDs to tests; maintainers SHALL keep the mapping in docs/testing.md.

#### Scenario: SCN-FO-01 trace
- **WHEN** file organizer unit test runs
- **THEN** it covers SCN-FO-01 per docs/testing.md

#### Scenario: SCN-WA golden trace
- **WHEN** `./scripts/evi-test whatsapp` runs
- **THEN** results match golden file for SCN-WA-04

#### Scenario: SCN-CHAT trace
- **WHEN** maintainer updates docs/testing.md
- **THEN** SCN-CHAT-02/03/04 map to `evi-test commitments` and `test_commitment_tools.py`

### Requirement: Commitment review verification
The project SHALL provide Tier 1 and Tier 2 tests for pending commitment list, confirm, and dismiss flows.

#### Scenario: SCN-CHAT-02 trace
- **WHEN** `./scripts/evi-test commitments` runs
- **THEN** `list_pending_commitments` returns seeded pending rows

#### Scenario: SCN-CHAT-03 trace
- **WHEN** `python3 tests/unit/test_commitment_tools.py` runs
- **THEN** confirm paths for event and task types are covered with mocked Windmill tools

#### Scenario: SCN-WA-10 trace
- **WHEN** `./scripts/evi-test commitments` runs with `DATABASE_URL` set
- **THEN** Postgres insert and list helpers succeed for a fixture commitment

### Requirement: Evolution filter unit tests
The project SHALL include unit tests for `evolution_filter` covering whitelist and dedupe behavior.

#### Scenario: SCN-WA-09
- **WHEN** `pytest tests/unit/test_evolution_filter.py` runs
- **THEN** all tests pass without network

### Requirement: LLM extract unit traceability
The project SHALL map SCN-WA-16 to a unit test with mocked Ollama (no network).

#### Scenario: SCN-WA-16 trace
- **WHEN** `pytest tests/unit/test_whatsapp_llm_extract.py` runs
- **THEN** fallback extraction for w005 passes with mocked LLM

### Requirement: Calendar list events live harness
The project SHALL provide `./scripts/evi-test calendar-list --live-windmill` for SCN-CAL-06 live verification.

#### Scenario: SCN-CAL-06 live
- **WHEN** `./scripts/evi-test calendar-list --live-windmill` runs with Windmill and gcal OAuth configured
- **THEN** `list_calendar_events` returns upcoming events or an empty-list message without failure prefix

### Requirement: OpenSpec backlog index
The project SHALL maintain `openspec/BACKLOG.md` as the ordered propose queue with status per change.

#### Scenario: SCN-DX-01
- **WHEN** a maintainer runs the architecture review ritual
- **THEN** `openspec/BACKLOG.md` lists completed and on-demand changes with current status

### Requirement: GitHub Actions offline smoke
The repository SHALL include a CI workflow that runs unit tests and `./scripts/evi-test smoke` without Docker or Ollama.

#### Scenario: SCN-CI-01
- **WHEN** `.github/workflows/ci.yml` runs on push to main
- **THEN** pytest and offline smoke complete successfully

#### Scenario: SCN-API trace
- **WHEN** `./scripts/evi-test smoke --full` runs with stack up
- **THEN** SCN-API-01 health check is included

### Requirement: E2E checklist
The project SHALL document Docker+Ollama validation steps in docs/testing.md.

#### Scenario: SCN-E2E-02
- **WHEN** offline smoke runs after a change
- **THEN** result is 14/14 PASS or skips documented

### Requirement: Windmill live traceability
docs/testing.md SHALL map Windmill live scenarios to evi-test commands.

#### Scenario: SCN-EMAIL-05 trace
- **WHEN** maintainer updates docs/testing.md
- **THEN** SCN-EMAIL-05 maps to `./scripts/evi-test email --live-windmill`

#### Scenario: SCN-TASK-05 trace
- **WHEN** maintainer updates docs/testing.md
- **THEN** SCN-TASK-05 maps to `./scripts/evi-test tasks --live-windmill`

### Requirement: JSONL log retention
Audit JSONL logs under `EVI_LOG_DIR` SHALL be trimmed to `EVI_LOG_MAX_AGE_DAYS` (default 7) after append operations.

#### Scenario: SCN-OPS-02
- **WHEN** `trim_jsonl` runs on `evolution_webhook.jsonl`
- **THEN** lines older than the configured max age are removed

### Requirement: Compose boot order
docker-compose SHALL define healthchecks for core data services and gate agent-api startup on healthy dependencies.

#### Scenario: SCN-OPS-01
- **WHEN** `docker compose up -d` runs on a clean stack
- **THEN** agent-api starts only after postgres, qdrant, and windmill-server report healthy

### Requirement: Prometheus metrics endpoint
When `EVI_METRICS_ENABLED` is true, agent-api SHALL expose `GET /metrics` with Prometheus text format including HTTP and webhook histograms.

#### Scenario: SCN-OPS-03
- **WHEN** client calls `GET /metrics` with metrics enabled
- **THEN** response includes `evi_http_requests_total` metric family

### Requirement: Runtime v3 offline harness
The project SHALL provide `./scripts/evi-test runtime-v3` validating workspace bootstrap, context assembly, skills, and tool registry wiring without network.

#### Scenario: SCN-UX-RUNTIME
- **WHEN** `./scripts/evi-test runtime-v3` runs offline
- **THEN** workspace files exist and `build_context` returns non-empty text

### Requirement: Inbox UX harness
The project SHALL provide `./scripts/evi-test inbox-ux` covering inbox format, delete_by_query mock, and session snapshot follow-up.

#### Scenario: SCN-UX-INBOX-01
- **WHEN** inbox-ux runs with `email_summary_messages.json`
- **THEN** formatted output includes message ids

#### Scenario: SCN-UX-INBOX-02
- **WHEN** delete_by_query is invoked with mocked Windmill
- **THEN** response reports deleted count without requiring user ids

#### Scenario: SCN-UX-INBOX-04
- **WHEN** tool snapshots exist for a session
- **THEN** `build_context` includes SESSION TOOL SNAPSHOTS block

### Requirement: LLM-first control channels
When `EVI_DIRECT_HANDLERS=false`, Telegram and WhatsApp control SHALL route inbox/review phrases through `invoke_chat`.

#### Scenario: SCN-UX-WA-CTRL-01
- **WHEN** `tests/unit/test_whatsapp_control.py` runs with default env
- **THEN** direct handler mocks are not called for review/inbox phrases
