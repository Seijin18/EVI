# WhatsApp message processing (fixture mode)

## ADDED Requirements

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

### Requirement: Live adapter (planned)
Live WhatsApp adapter is REMOVED from v1; options documented in `remote-access` change design.
