## ADDED Requirements

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
