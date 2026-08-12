## ADDED Requirements

### Requirement: Per-session conversation memory
The system SHALL keep bounded conversation memory keyed by `session_id`, so that concurrent turns for different sessions never observe each other's messages. `session_lane` continues to serialize turns within one `session_id`.

#### Scenario: SCN-RT-03
- **WHEN** `./scripts/evi-test sessions` interleaves two `session_id` values through `/chat`
- **THEN** each session's assembled history contains only its own messages

## MODIFIED Requirements

### Requirement: Memory reset
The system SHALL expose `POST /reset` clearing bounded in-memory history for the requested session only, and SHALL require `X-Api-Key` when `EVI_API_KEY` is set.

#### Scenario: SCN-RESET-01
- **WHEN** client calls `POST /reset` with a `session_id`
- **THEN** bounded memory for that session is cleared and other sessions are untouched

### Requirement: Notes
The system SHALL expose `POST /note` saving Markdown notes to inbox_ia, requiring `X-Api-Key` when `EVI_API_KEY` is set.

#### Scenario: SCN-NOTE-01
- **WHEN** valid note payload is posted with a valid key
- **THEN** a Markdown file is written under inbox_ia

### Requirement: Session insight
The system SHALL expose `POST /insight` generating auto-insight Markdown, requiring `X-Api-Key` when `EVI_API_KEY` is set.

#### Scenario: SCN-INSIGHT-01
- **WHEN** insight is requested for an active session with a valid key
- **THEN** response includes generated insight content or a documented stub
