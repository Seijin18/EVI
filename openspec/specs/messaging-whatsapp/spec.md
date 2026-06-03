# WhatsApp message processing (fixture mode)

## Purpose

Extract calendar tasks and events from WhatsApp text via fixtures and Evolution API webhooks.

## Requirements

### Requirement: Fixture pipeline
The processor SHALL read `tests/fixtures/whatsapp/messages.jsonl` and extract commitments without live WhatsApp API.

#### Scenario: SCN-WA-01
- **GIVEN** message w001 (meeting tomorrow 14h)
- **WHEN** extract runs
- **THEN** type=event, date=2026-06-04, time=14:00

#### Scenario: SCN-WA-02
- **GIVEN** message w002 (report by Friday)
- **WHEN** extract runs
- **THEN** type=task, due=2026-06-05 (Friday after ref date 2026-06-03)

#### Scenario: SCN-WA-03
- **GIVEN** message w004 ("Ok, combinado")
- **WHEN** extract runs
- **THEN** no commitment is produced

#### Scenario: SCN-WA-04
- **WHEN** `./scripts/evi-test whatsapp` runs
- **THEN** results match `tests/golden/whatsapp_commitments.json` and JSONL log is written

### Requirement: Evolution API live adapter
The system SHALL accept Evolution API webhooks at `POST /webhooks/evolution` and extract commitments.

#### Scenario: SCN-WA-05
- **WHEN** `evi-test evolution` runs with fixture payload
- **THEN** at least one message is parsed and commitment extracted
