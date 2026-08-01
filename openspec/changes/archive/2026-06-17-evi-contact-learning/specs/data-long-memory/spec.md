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

### Requirement: Postgres contact registry
The system SHALL persist WhatsApp contact identity (display name, aliases, phone) in Postgres (`whatsapp_contacts`), synced from Evolution, and expose `set_whatsapp_contact_name` to assign a display name/alias by JID. Postgres is the canonical source for contact identity; the filesystem (`contact_filesystem`) remains canonical for timeline/narrative memory.

#### Scenario: SCN-MEM-08
- **WHEN** `tests/unit/test_contact_registry.py` runs
- **THEN** contacts can be searched by agenda name/alias and merged with filesystem-known contacts via `collect_known_contacts`

### Requirement: Evolution contact and chat discovery
The system SHALL expose tools to list and summarize recent WhatsApp chats/contacts via Evolution `findContacts`/`findChats`, independent of contacts already known to filesystem or Postgres memory.

#### Scenario: SCN-MEM-09
- **WHEN** `tests/unit/test_evolution_discovery.py` runs
- **THEN** discovery service returns contacts/chats from the Evolution API response shape without requiring prior local memory

### Requirement: Commitment replay from ingest log
The system SHALL be able to replay `evolution_webhook.jsonl` ingest lines to backfill `pending_commitments` and contact timeline entries that were missed by the live webhook filter or Evolution cache lag.

#### Scenario: SCN-MEM-10
- **WHEN** `tests/unit/test_commitment_replay.py` runs
- **THEN** commitments extracted from replayed ingest lines are queued without duplicating already-processed messages
