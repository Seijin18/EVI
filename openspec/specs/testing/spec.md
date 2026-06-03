# Testing requirements

## ADDED Requirements

### Requirement: Tiered verification
Every feature domain MUST have Tier 1 (pytest) and Tier 2 (`./scripts/evi-test <feature>`) coverage before OpenSpec archive.

#### Scenario: Unit suite
- **WHEN** `pytest tests/unit -q` runs
- **THEN** all SCN-marked unit tests pass without network

#### Scenario: Offline smoke
- **WHEN** `./scripts/evi-test smoke` runs without Docker
- **THEN** memory, file-organizer, whatsapp, calendar (mock), notes, telegram parse pass

### Requirement: Scenario traceability
Domain specs reference scenario IDs mapped to tests:

| ID | Feature | Test |
|----|---------|------|
| SCN-FO-01 | File classify university PDF | `tests/unit/test_file_organizer.py` |
| SCN-WA-01 | WhatsApp meeting tomorrow | `tests/unit/test_whatsapp_processor.py` |
| SCN-WA-02 | WhatsApp task by Friday | same |
| SCN-WA-03 | Skip acknowledgement | same |
| SCN-WA-04 | Golden pipeline | `evi-test whatsapp` |
| SCN-API-01 | Health endpoint | `evi-test smoke` (with `--full`) |
| SCN-NOTE-01 | Manual note file | `evi-test notes` |
