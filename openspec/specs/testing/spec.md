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

#### Scenario: SCN-API trace
- **WHEN** `./scripts/evi-test smoke --full` runs with stack up
- **THEN** SCN-API-01 health check is included

### Requirement: E2E checklist
The project SHALL document Docker+Ollama validation steps in docs/testing.md.

#### Scenario: SCN-E2E-02
- **WHEN** offline smoke runs after a change
- **THEN** result is 13/13 PASS or skips documented
