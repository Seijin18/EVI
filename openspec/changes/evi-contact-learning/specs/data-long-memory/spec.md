## ADDED Requirements

### Requirement: Contact learning by name
The system SHALL expose LangGraph tools to list, inspect, and learn WhatsApp contacts by display name or phone without requiring JID from the user.

#### Scenario: SCN-MEM-06
- **WHEN** `./scripts/evi-test contact-learning` runs
- **THEN** contact resolution, mocked synthesis, and registry wiring pass offline

### Requirement: Evolution message backfill
When learning a contact with fetch enabled, the system SHALL call Evolution findMessages and append new rows to timeline.jsonl with dedupe by source_id.

#### Scenario: SCN-MEM-07
- **WHEN** `./scripts/evi-test contact-learning` or unit backfill tests run
- **THEN** timeline entries include optional `backfill` flag and respect `EVI_BACKFILL_MAX_MESSAGES`
