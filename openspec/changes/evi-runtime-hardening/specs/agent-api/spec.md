## ADDED Requirements

### Requirement: Per-session conversation memory
The system SHALL keep bounded conversation memory keyed by `session_id`, so that concurrent turns for different sessions never observe each other's messages. `session_lane` continues to serialize turns within one `session_id`. The registry SHALL be bounded by `EVI_SESSION_MEMORY_MAX` (default 32) with LRU eviction, and a trim callback bound to one session SHALL NOT fire for another — `clear()` drops it.

#### Scenario: SCN-RT-03
- **WHEN** `./scripts/evi-test sessions` interleaves two `session_id` values through `/chat`
- **THEN** each session's assembled history contains only its own messages, no trim callback crosses sessions, and the registry stays within `EVI_SESSION_MEMORY_MAX`

## MODIFIED Requirements

### Requirement: Memory reset
The system SHALL expose `POST /reset` clearing bounded in-memory history for the requested session only — resolved from an optional `session_id` body field, the `X-Session-Id` header, or the default session — and SHALL require `X-Api-Key` when `EVI_API_KEY` is set.

#### Scenario: SCN-RESET-01
- **WHEN** client calls `POST /reset` with a `session_id`
- **THEN** bounded memory for that session is cleared, the response echoes `session_id`, and other sessions are untouched

### Requirement: Notes
The system SHALL expose `POST /note` saving Markdown notes to inbox_ia, requiring `X-Api-Key` when `EVI_API_KEY` is set.

#### Scenario: SCN-NOTE-01
- **WHEN** valid note payload is posted with a valid key
- **THEN** a Markdown file is written under inbox_ia

### Requirement: Session insight
The system SHALL expose `POST /insight` generating auto-insight Markdown from the requested session's own memory, requiring `X-Api-Key` when `EVI_API_KEY` is set.

#### Scenario: SCN-INSIGHT-01
- **WHEN** insight is requested for an active session with a valid key
- **THEN** response includes generated insight content or a documented stub, built only from that session's turns
