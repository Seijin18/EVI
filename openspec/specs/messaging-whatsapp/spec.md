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

### Requirement: WhatsApp group whitelist
When `EVI_WHATSAPP_SKIP_GROUPS` is true, the Evolution filter SHALL allow messages from group JIDs listed in `EVI_WHATSAPP_GROUP_WHITELIST` (comma-separated `@g.us` ids) and SHALL ignore other groups.

#### Scenario: SCN-WA-06
- **GIVEN** whitelist contains `120363012345678901@g.us`
- **WHEN** filter runs on a group message with that JID
- **THEN** message is retained for processing

#### Scenario: SCN-WA-07
- **GIVEN** whitelist contains `120363012345678901@g.us`
- **WHEN** filter runs on a different `@g.us` JID
- **THEN** message is skipped as a group

### Requirement: Evolution groupsIgnore coordination
When `EVI_WHATSAPP_GROUP_WHITELIST` is non-empty, `setup-evolution.sh` SHALL set `groupsIgnore=false` so whitelisted groups reach the webhook.

#### Scenario: SCN-WA-08
- **WHEN** setup script runs with non-empty whitelist in environment
- **THEN** Evolution instance config disables `groupsIgnore`

### Requirement: Pending commitment queue
Extracted commitments from Evolution webhooks SHALL be persisted to Postgres `pending_commitments` with status `pending` and priority classification.

#### Scenario: SCN-WA-10
- **WHEN** Evolution webhook extracts a commitment
- **THEN** a row is inserted (or deduped by source_id) and response includes `queued` count

#### Scenario: SCN-WA-11
- **WHEN** commitment text contains urgency keywords
- **THEN** priority is classified as `urgent`, `work`, or `university` when matched

### Requirement: Evolution webhook log observability
Evolution webhook processing SHALL write JSONL audit lines with processing timestamp `ts` and WhatsApp message time `message_ts` when available.

#### Scenario: SCN-WA-13
- **WHEN** a message is ingested after filtering
- **THEN** log line includes `step: ingest`, `message_ts`, `sender`, `from_me`, `is_group`

#### Scenario: SCN-WA-14
- **WHEN** a parsed message is dropped by `evolution_filter`
- **THEN** log line includes `step: filtered_out`, `reason`, and `message_ts`

#### Scenario: SCN-WA-15
- **WHEN** `messages.upsert` yields zero parsed messages
- **THEN** skip log MAY include `hint: parser_empty_text_or_unsupported_type`

### Requirement: Pending commitment notifications
The system SHALL notify via Telegram when configured and either 5+ unnotified pending items exist or a new item has high priority.

#### Scenario: SCN-WA-12
- **WHEN** `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set and notification threshold is met
- **THEN** a digest message is sent via Telegram Bot API
