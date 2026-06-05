## ADDED Requirements

### Requirement: Commitment review verification
The project SHALL provide Tier 1 and Tier 2 tests for pending commitment list, confirm, and dismiss flows.

#### Scenario: SCN-CHAT-02 trace
- **WHEN** `./scripts/evi-test commitments` runs
- **THEN** `list_pending_commitments` returns seeded pending rows

#### Scenario: SCN-CHAT-03 trace
- **WHEN** `pytest tests/unit/test_commitment_tools.py` runs
- **THEN** confirm paths for event and task types are covered with mocked Windmill tools

#### Scenario: SCN-WA-10 trace
- **WHEN** `./scripts/evi-test commitments` runs with `DATABASE_URL` set
- **THEN** Postgres insert and list helpers succeed for a fixture commitment

## MODIFIED Requirements

### Requirement: Tiered verification
Every feature domain MUST have Tier 1 (pytest) and Tier 2 (`./scripts/evi-test <feature>`) coverage before OpenSpec archive.

#### Scenario: Unit suite
- **WHEN** `pytest tests/unit -q` runs
- **THEN** all SCN-marked unit tests pass without network

#### Scenario: Offline smoke
- **WHEN** `./scripts/evi-test smoke` runs without Docker
- **THEN** memory, file-organizer, whatsapp, calendar (mock), notes, telegram parse pass

#### Scenario: Commitments smoke inclusion
- **WHEN** `./scripts/evi-test smoke` runs with `DATABASE_URL` available
- **THEN** commitments feature is included in smoke or documented as optional with DATABASE_URL

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
