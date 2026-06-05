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

#### Scenario: SCN-API trace
- **WHEN** `./scripts/evi-test smoke --full` runs with stack up
- **THEN** SCN-API-01 health check is included

### Requirement: E2E checklist
The project SHALL document Docker+Ollama validation steps in docs/testing.md.

#### Scenario: SCN-E2E-02
- **WHEN** offline smoke runs after a change
- **THEN** result is 13/13 PASS or skips documented

### Requirement: Windmill live traceability
docs/testing.md SHALL map Windmill live scenarios to evi-test commands.

#### Scenario: SCN-EMAIL-05 trace
- **WHEN** maintainer updates docs/testing.md
- **THEN** SCN-EMAIL-05 maps to `./scripts/evi-test email --live-windmill`

#### Scenario: SCN-TASK-05 trace
- **WHEN** maintainer updates docs/testing.md
- **THEN** SCN-TASK-05 maps to `./scripts/evi-test tasks --live-windmill`

### Requirement: Compose boot order
docker-compose SHALL define healthchecks for core data services and gate agent-api startup on healthy dependencies.

#### Scenario: SCN-OPS-01
- **WHEN** `docker compose up -d` runs on a clean stack
- **THEN** agent-api starts only after postgres, qdrant, and windmill-server report healthy
